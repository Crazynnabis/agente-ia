# agente_financiero/digestor_maestro.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from nucleo.cliente_ia import chat
from agente_financiero.digestor_tecnico import ejecutar_ciclo_tecnico
from agente_financiero.digestor_tecnico_avanzado import ejecutar_ciclo_avanzado
from agente_financiero.digestor_riesgo import ejecutar_digestor_riesgo
from agente_financiero.horario_trading import debe_operar
from agente_financiero.backtesting import backtest_rapido
from agente_financiero.logger_trading import log_ciclo, obtener_estadisticas_dia

ACTIVOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

async def ejecutar_ciclo_maestro() -> dict:
    inicio = datetime.now()
    timestamp = inicio.strftime("%H:%M:%S")
    print(f"\n{'='*60}")
    print(f"[MAESTRO] Ciclo maestro iniciado: {timestamp}")
    print(f"{'='*60}")

    # Verifica horario antes de todo
    horario = debe_operar()
    if not horario["operar"]:
        print(f"[MAESTRO] Fuera de horario: {horario['razon']}")
        return {
            "timestamp":  timestamp,
            "operar":     False,
            "razon":      horario["razon"],
            "decisiones": [],
        }

    print(f"[MAESTRO] Horario: {horario.get('razon','N/A')} | Score: {horario.get('score','N/A')}/10")

    # Ejecuta ambos ciclos en paralelo
    print("\n[MAESTRO] Ejecutando ciclos técnico y avanzado en paralelo...")
    ciclo_basico, ciclo_avanzado = await asyncio.gather(
        ejecutar_ciclo_tecnico(),
        ejecutar_ciclo_avanzado(),
    )

    # Consolida señales de ambos ciclos por simbolo
    tabla_maestra = []
    for simbolo in ACTIVOS:
        basico   = next((t for t in ciclo_basico["tabla"]   if t.get("simbolo") == simbolo), {})
        avanzado = next((t for t in ciclo_avanzado["tabla"] if t.get("simbolo") == simbolo), {})

        if not basico and not avanzado:
            continue

        # Señales de cada ciclo
        señal_basico   = basico.get("señal_final", "ESPERAR")
        señal_avanzado = avanzado.get("señal_final", "ESPERAR")
        conf_basico    = basico.get("confianza_final", 50)
        conf_avanzado  = avanzado.get("confianza", 50)

        # Sistema de ponderacion
        # Basico vale 60% (mas fuentes), avanzado 40% (mas profundo)
        votos_compra = sum([
            señal_basico   == "COMPRAR",
            señal_avanzado == "COMPRAR",
        ])
        votos_venta = sum([
            señal_basico   == "VENDER",
            señal_avanzado == "VENDER",
        ])

        # Confianza ponderada
        confianza_ponderada = round((conf_basico * 0.6) + (conf_avanzado * 0.4))

        if votos_compra == 2:
            señal_maestra = "COMPRAR"
            confluencia   = "MUY_ALTA"
            confianza_final = min(confianza_ponderada + 15, 99)
        elif votos_venta == 2:
            señal_maestra = "VENDER"
            confluencia   = "MUY_ALTA"
            confianza_final = min(confianza_ponderada + 15, 99)
        elif votos_compra == 1 and señal_basico == "COMPRAR":
            señal_maestra = "COMPRAR"
            confluencia   = "MEDIA"
            confianza_final = confianza_ponderada
        elif votos_venta == 1 and señal_basico == "VENDER":
            señal_maestra = "VENDER"
            confluencia   = "MEDIA"
            confianza_final = confianza_ponderada
        else:
            señal_maestra = "ESPERAR"
            confluencia   = "BAJA"
            confianza_final = max(confianza_ponderada - 20, 10)

        # Stop loss y take profit del ciclo basico (tiene ATR)
        stop_loss   = basico.get("stop_loss", 0)
        take_profit1 = basico.get("take_profit_1", 0)
        take_profit2 = basico.get("take_profit_2", 0)
        precio       = basico.get("precio", avanzado.get("precio", 0))

        # Mejora stop loss con niveles del volume profile
        vp_val = avanzado.get("val", 0)
        vp_vah = avanzado.get("vah", 0)
        if señal_maestra == "COMPRAR" and vp_val > 0 and vp_val > stop_loss:
            stop_loss = vp_val
        elif señal_maestra == "VENDER" and vp_vah > 0 and vp_vah < stop_loss:
            stop_loss = vp_vah

        tabla_maestra.append({
            "simbolo":        simbolo,
            "precio":         precio,
            "señal_maestra":  señal_maestra,
            "confluencia":    confluencia,
            "confianza_final": confianza_final,
            "votos_compra":   votos_compra,
            "votos_venta":    votos_venta,
            "señal_basico":   señal_basico,
            "señal_avanzado": señal_avanzado,
            "conf_basico":    conf_basico,
            "conf_avanzado":  conf_avanzado,
            "stop_loss":      stop_loss,
            "take_profit_1":  take_profit1,
            "take_profit_2":  take_profit2,
        })

    # Filtra señales fuertes
    señales_fuertes = [
        t for t in tabla_maestra
        if t["confluencia"] in ["MUY_ALTA", "ALTA"] and t["confianza_final"] >= 70
    ]

    print(f"\n[MAESTRO] Señales fuertes: {len(señales_fuertes)}")

    # Pasa señales fuertes por filtro de riesgo
    señales_para_riesgo = []
    for s in señales_fuertes:
        señales_para_riesgo.append({
            "simbolo":        s["simbolo"],
            "señal_final":    s["señal_maestra"],
            "precio":         s["precio"],
            "stop_loss":      s["stop_loss"],
            "take_profit_1":  s["take_profit_1"],
            "take_profit_2":  s["take_profit_2"],
            "confianza_final": s["confianza_final"],
            "confluencia":    s["confluencia"],
        })

    resultado_riesgo = await ejecutar_digestor_riesgo(señales_para_riesgo)
    señales_aprobadas = resultado_riesgo.get("señales_aprobadas", [])

    # Genera decision maestra con IA
    resumen_tabla = "\n".join([
        f"{t['simbolo']}: {t['señal_maestra']} | conf={t['confianza_final']}% | {t['confluencia']} | "
        f"basico={t['señal_basico']}({t['conf_basico']}%) avanzado={t['señal_avanzado']}({t['conf_avanzado']}%) | "
        f"precio={t['precio']} SL={t['stop_loss']} TP1={t['take_profit_1']}"
        for t in tabla_maestra
    ])

    print("[MAESTRO] Generando decision maestra con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"TABLA MAESTRA:\n{resumen_tabla}\n\nSEÑALES APROBADAS POR RIESGO: {len(señales_aprobadas)}"}],
        system="""Eres el cerebro maestro de un sistema de trading algoritmico profesional.
Recibes el analisis consolidado de dos sistemas: tecnico basico (velas+indicadores+orderflow+niveles+onchain) y tecnico avanzado (funding+liquidaciones+estructura+volume_profile).
Tu funcion es tomar la decision final de trading.

Entrega SOLO decisiones con confluencia MUY_ALTA o ALTA y confianza mayor a 70%.
Formato:
DECISION_MAESTRA_N:
- ACCION: COMPRAR o VENDER
- SIMBOLO: nombre
- PRECIO_ENTRADA: numero
- STOP_LOSS: numero
- TAKE_PROFIT_1: numero (ratio minimo 2:1)
- TAKE_PROFIT_2: numero (ratio minimo 3:1)
- CONFIANZA_SISTEMA: porcentaje
- SISTEMAS_CONFIRMACION: basico y/o avanzado
- RAZON_MAESTRA: dos oraciones explicando por que es la mejor entrada ahora
- HORIZONTE: timeframe optimo
- PRIORIDAD: 1 (mas urgente) a 3

Si no hay señales: SISTEMA_EN_ESPERA
Responde en español sin texto adicional.""",
        max_tokens=1000
    )

    duracion = (datetime.now() - inicio).total_seconds()
    stats    = obtener_estadisticas_dia()

    log_ciclo(
        ciclo_num=stats.get("total_ordenes", 0) + 1,
        señales_detectadas=len(señales_fuertes),
        ordenes_ejecutadas=len(señales_aprobadas),
        duracion_segundos=duracion,
        modelo_usado=respuesta.get("modelo", "N/A")
    )

    
    # Ejecuta ordenes aprobadas en Alpaca
    from agente_financiero.ejecutor_alpaca import ejecutar_orden, obtener_portafolio
    ordenes_ejecutadas = []
    for señal in señales_aprobadas:
        t = señal.get("tamaño_posicion", {})
        if t.get("cantidad", 0) > 0:
            orden = ejecutar_orden(
                simbolo=señal["simbolo"],
                accion=señal["accion"],
                cantidad=t["cantidad"],
                precio_entrada=señal["precio"],
                stop_loss=señal["stop_loss"],
                take_profit=señal["take_profit_1"],
                atr=señal.get("atr_pct", 0)
            )
            ordenes_ejecutadas.append(orden)
            print(f"[MAESTRO] Orden ejecutada: {señal['simbolo']} {señal['accion']}")

    return {
        "timestamp":         timestamp,
        "duracion_segundos": round(duracion, 1),
        "horario":           horario,
        "tabla_maestra":     tabla_maestra,
        "señales_fuertes":   señales_fuertes,
        "señales_aprobadas": señales_aprobadas,
        "ordenes_ejecutadas": ordenes_ejecutadas,
        "decision_maestra":  respuesta["texto"],
        "modelo":            respuesta["modelo"],
        "estadisticas_dia":  stats,
    }