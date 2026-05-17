# agente_financiero/digestor_maestro.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from nucleo.cliente_ia import chat
from agente_financiero.digestor_tecnico import ejecutar_ciclo_tecnico
from agente_financiero.digestor_tecnico_avanzado import ejecutar_ciclo_avanzado
from agente_financiero.digestor_estrategias import ejecutar_ciclo_estrategias
from agente_financiero.digestor_contexto import ejecutar_ciclo_contexto
from agente_financiero.digestor_riesgo import ejecutar_digestor_riesgo
from agente_financiero.horario_trading import debe_operar
from agente_financiero.logger_trading import log_ciclo, obtener_estadisticas_dia

ACTIVOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

async def ejecutar_ciclo_maestro() -> dict:
    inicio    = datetime.now()
    timestamp = inicio.strftime("%H:%M:%S")
    print(f"\n{'='*60}")
    print(f"[MAESTRO] Ciclo maestro iniciado: {timestamp}")
    print(f"{'='*60}")

    horario = debe_operar()
    if not horario["operar"]:
        print(f"[MAESTRO] Fuera de horario: {horario['razon']}")
        return {"timestamp": timestamp, "operar": False, "razon": horario["razon"], "decisiones": []}

    print(f"[MAESTRO] Horario: {horario.get('razon','N/A')} | Score: {horario.get('score','N/A')}/10")

    print("\n[MAESTRO] Ejecutando todos los ciclos en paralelo...")
    ciclo_basico, ciclo_avanzado, ciclo_estrategias, ciclo_contexto = await asyncio.gather(
        ejecutar_ciclo_tecnico(),
        ejecutar_ciclo_avanzado(),
        ejecutar_ciclo_estrategias(),
        ejecutar_ciclo_contexto(),
    )

    print(f"[MAESTRO] Tecnico: {len(ciclo_basico['señales_fuertes'])} señales")
    print(f"[MAESTRO] Avanzado: {len(ciclo_avanzado['señales_fuertes'])} señales")
    print(f"[MAESTRO] Estrategias: {len(ciclo_estrategias['señales_fuertes'])} señales")
    print(f"[MAESTRO] Contexto: {ciclo_contexto['sesgo_contexto']} | F&G={ciclo_contexto['fear_greed'].get('valor_hoy','N/A')}")

    tabla_maestra = []
    for simbolo in ACTIVOS:
        basico     = next((t for t in ciclo_basico["tabla"]           if t.get("simbolo") == simbolo), {})
        avanzado   = next((t for t in ciclo_avanzado["tabla"]         if t.get("simbolo") == simbolo), {})
        estrategia = next((t for t in ciclo_estrategias["resultados"] if t.get("simbolo") == simbolo), {})

        señal_basico     = basico.get("señal_final", "ESPERAR")
        señal_avanzado   = avanzado.get("señal_final", "ESPERAR")
        señal_estrategia = estrategia.get("señal_final", "ESPERAR")
        sesgo_contexto   = ciclo_contexto.get("sesgo_contexto", "NEUTRAL")
        conf_basico      = basico.get("confianza_final", 50)
        conf_avanzado    = avanzado.get("confianza", 50)
        conf_estrategia  = estrategia.get("confianza", 50)

        contexto_alineado = (
            (sesgo_contexto == "ALCISTA" and señal_basico == "COMPRAR") or
            (sesgo_contexto == "BAJISTA" and señal_basico == "VENDER") or
            sesgo_contexto == "NEUTRAL"
        )

        votos_compra = sum([
            señal_basico     == "COMPRAR",
            señal_avanzado   == "COMPRAR",
            señal_estrategia == "COMPRAR",
            contexto_alineado and sesgo_contexto == "ALCISTA",
        ])
        votos_venta = sum([
            señal_basico     == "VENDER",
            señal_avanzado   == "VENDER",
            señal_estrategia == "VENDER",
            contexto_alineado and sesgo_contexto == "BAJISTA",
        ])

        confianza_ponderada = round((conf_basico * 0.4) + (conf_avanzado * 0.3) + (conf_estrategia * 0.3))

        if votos_compra >= 3:
            señal_maestra   = "COMPRAR"
            confluencia     = "MUY_ALTA"
            confianza_final = min(confianza_ponderada + 20, 99)
        elif votos_compra >= 2:
            señal_maestra   = "COMPRAR"
            confluencia     = "ALTA"
            confianza_final = min(confianza_ponderada + 10, 99)
        elif votos_venta >= 3:
            señal_maestra   = "VENDER"
            confluencia     = "MUY_ALTA"
            confianza_final = min(confianza_ponderada + 20, 99)
        elif votos_venta >= 2:
            señal_maestra   = "VENDER"
            confluencia     = "ALTA"
            confianza_final = min(confianza_ponderada + 10, 99)
        else:
            señal_maestra   = "ESPERAR"
            confluencia     = "BAJA"
            confianza_final = max(confianza_ponderada - 20, 10)

        stop_loss    = basico.get("stop_loss", 0)
        take_profit1 = basico.get("take_profit_1", 0)
        take_profit2 = basico.get("take_profit_2", 0)
        precio       = basico.get("precio", avanzado.get("precio", 0))

        vp_val = avanzado.get("val", 0)
        vp_vah = avanzado.get("vah", 0)
        if señal_maestra == "COMPRAR" and vp_val > 0 and vp_val > stop_loss:
            stop_loss = vp_val
        elif señal_maestra == "VENDER" and vp_vah > 0 and vp_vah < stop_loss:
            stop_loss = vp_vah

        tabla_maestra.append({
            "simbolo":          simbolo,
            "precio":           precio,
            "señal_maestra":    señal_maestra,
            "confluencia":      confluencia,
            "confianza_final":  confianza_final,
            "votos_compra":     votos_compra,
            "votos_venta":      votos_venta,
            "señal_basico":     señal_basico,
            "señal_avanzado":   señal_avanzado,
            "señal_estrategia": señal_estrategia,
            "sesgo_contexto":   sesgo_contexto,
            "conf_basico":      conf_basico,
            "conf_avanzado":    conf_avanzado,
            "conf_estrategia":  conf_estrategia,
            "stop_loss":        stop_loss,
            "take_profit_1":    take_profit1,
            "take_profit_2":    take_profit2,
        })

    señales_fuertes = [
        t for t in tabla_maestra
        if t["confluencia"] in ["MUY_ALTA", "ALTA"] and t["confianza_final"] >= 70
    ]

    print(f"\n[MAESTRO] Señales fuertes: {len(señales_fuertes)}")

    señales_para_riesgo = []
    for s in señales_fuertes:
        señales_para_riesgo.append({
            "simbolo":         s["simbolo"],
            "señal_final":     s["señal_maestra"],
            "señal_basico":    s["señal_basico"],
            "señal_avanzado":  s["señal_avanzado"],
            "señal_estrategia":s["señal_estrategia"],
            "sesgo_contexto":  s["sesgo_contexto"],
            "precio":          s["precio"],
            "stop_loss":       s["stop_loss"],
            "take_profit_1":   s["take_profit_1"],
            "take_profit_2":   s["take_profit_2"],
            "confianza_final": s["confianza_final"],
            "confluencia":     s["confluencia"],
        })

    resultado_riesgo  = await ejecutar_digestor_riesgo(
        señales_para_riesgo,
        sesgo_contexto=ciclo_contexto.get("sesgo_contexto", "NEUTRAL")
    )
    señales_aprobadas = resultado_riesgo.get("señales_aprobadas", [])

    resumen_tabla = "\n".join([
        f"{t['simbolo']}: {t['señal_maestra']} | conf={t['confianza_final']}% | {t['confluencia']} | "
        f"votos C={t['votos_compra']} V={t['votos_venta']} | "
        f"tecnico={t['señal_basico']} avanzado={t['señal_avanzado']} "
        f"estrategia={t['señal_estrategia']} contexto={t['sesgo_contexto']} | "
        f"precio={t['precio']} SL={t['stop_loss']} TP1={t['take_profit_1']} TP2={t['take_profit_2']}"
        for t in tabla_maestra
    ])

    resumen_contexto = f"""
CONTEXTO GLOBAL:
Fear & Greed: {ciclo_contexto['fear_greed'].get('valor_hoy','N/A')} ({ciclo_contexto['fear_greed'].get('clasificacion','N/A')})
Sesgo mercado: {ciclo_contexto['sesgo_contexto']} | Confianza: {ciclo_contexto['confianza_contexto']}%
WTI Petroleo: ${ciclo_contexto['wti_precio']} ({ciclo_contexto['wti_cambio']}% hoy)
Analisis: {ciclo_contexto['analisis_consolidado'][:300]}
"""

    print("[MAESTRO] Generando decision maestra con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"TABLA MAESTRA:\n{resumen_tabla}\n\n{resumen_contexto}\n\nSEÑALES APROBADAS POR RIESGO: {len(señales_aprobadas)}"}],
        system="Eres el cerebro maestro de un sistema de trading algoritmico profesional. Recibes analisis de 4 sistemas: 1.TECNICO BASICO: velas+indicadores+orderflow+niveles+onchain 2.TECNICO AVANZADO: funding+liquidaciones+estructura+volume_profile 3.ESTRATEGIAS: ORB+VWAP+Gap+MeanReversion+NewsMomentum 4.CONTEXTO: sentimiento+macro+fundamental+historico+petroleo. Prioriza señales donde al menos 3 sistemas coinciden. El contexto actua como filtro. Entrega SOLO decisiones con confluencia MUY_ALTA o ALTA y confianza mayor a 70%. Formato: DECISION_MAESTRA_N: - ACCION: COMPRAR o VENDER - SIMBOLO: nombre - PRECIO_ENTRADA: numero - STOP_LOSS: numero - TAKE_PROFIT_1: numero - TAKE_PROFIT_2: numero - CONFIANZA_SISTEMA: porcentaje - SISTEMAS_CONFIRMACION: cuales sistemas confirman - RAZON_MAESTRA: dos oraciones - HORIZONTE: timeframe - PRIORIDAD: 1 a 3. Si no hay señales: SISTEMA_EN_ESPERA. Responde en español sin texto adicional.",
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

    from agente_financiero.ejecutor_alpaca import ejecutar_orden
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
        "timestamp":          timestamp,
        "duracion_segundos":  round(duracion, 1),
        "horario":            horario,
        "tabla_maestra":      tabla_maestra,
        "señales_fuertes":    señales_fuertes,
        "señales_aprobadas":  señales_aprobadas,
        "ordenes_ejecutadas": ordenes_ejecutadas,
        "decision_maestra":   respuesta["texto"],
        "modelo":             respuesta["modelo"],
        "estadisticas_dia":   stats,
    }