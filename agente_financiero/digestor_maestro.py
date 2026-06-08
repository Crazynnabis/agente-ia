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

DEFAULTS = {
    "tecnico":     {"tabla": [], "senales_fuertes": [], "onchain": {}, "decisiones": "SIN_SENALES_FUERTES", "modelo": "fallback"},
    "avanzado":    {"tabla": [], "senales_fuertes": [], "decisiones": "SIN_SENALES_AVANZADAS", "modelo": "fallback"},
    "estrategias": {"resultados": [], "senales_fuertes": [], "decisiones": "SIN_SENALES_ESTRATEGIAS", "modelo": "fallback"},
    "contexto":    {"sesgo_contexto": "NEUTRAL", "confianza_contexto": 50, "fear_greed": {},
                    "wti_precio": 0, "wti_cambio": 0, "analisis_consolidado": "Sin datos",
                    "estac_senal": "NEUTRAL", "pcr_btc": 1.0, "maxpain_btc": "N/A"},
}

# ============================================================
# CONTEXTO HISTÓRICO — aprende de señales pasadas
# ============================================================
def obtener_historial_reciente() -> str:
    """
    Lee las últimas 10 señales de Supabase con sus resultados.
    Devuelve un resumen para incluir en el prompt del digestor_maestro.
    """
    try:
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

        # Últimas 10 señales del día con resultado conocido
        res = sb.table("senales_trading").select(
            "simbolo, accion, precio, confianza, aprobada_riesgo, "
            "take_profit_1, stop_loss, timestamp, razon"
        ).order("timestamp", desc=True).limit(10).execute()

        if not res.data:
            return "Sin historial de señales previas hoy."

        lineas = ["HISTORIAL RECIENTE (últimas señales):"]
        ganadoras = 0
        perdedoras = 0

        for s in res.data:
            simbolo   = s.get("simbolo", "?")
            accion    = s.get("accion", "?")
            precio    = s.get("precio", 0)
            confianza = s.get("confianza", 0)
            aprobada  = s.get("aprobada_riesgo", False)
            tp1       = s.get("take_profit_1", 0)
            sl        = s.get("stop_loss", 0)
            ts        = s.get("timestamp", "")[:16] if s.get("timestamp") else ""

            estado = "✅ aprobada" if aprobada else "❌ rechazada"
            lineas.append(
                f"  {ts} | {simbolo} {accion} | conf={confianza}% | "
                f"precio={precio} SL={sl} TP={tp1} | {estado}"
            )

        # Win rate del día desde inversiones
        res_inv = sb.table("inversiones").select(
            "simbolo, ganancia_pct, resultado"
        ).order("timestamp", desc=True).limit(20).execute()

        if res_inv.data:
            for inv in res_inv.data:
                resultado = inv.get("resultado", "")
                if resultado == "ganancia":
                    ganadoras += 1
                elif resultado == "perdida":
                    perdedoras += 1

            total = ganadoras + perdedoras
            if total > 0:
                win_rate = round(ganadoras / total * 100)
                lineas.append(f"\nWIN RATE HOY: {win_rate}% ({ganadoras}G / {perdedoras}P de {total} ops)")

        return "\n".join(lineas)

    except Exception as e:
        return f"Historial no disponible: {e}"


def obtener_winrate_por_activo() -> str:
    """Win rate por activo para ajustar confianza en la decision."""
    try:
        from supabase import create_client
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

        res = sb.table("inversiones").select(
            "simbolo, resultado"
        ).order("timestamp", desc=True).limit(50).execute()

        if not res.data:
            return ""

        stats = {}
        for inv in res.data:
            simbolo   = inv.get("simbolo", "?")
            resultado = inv.get("resultado", "")
            if simbolo not in stats:
                stats[simbolo] = {"g": 0, "p": 0}
            if resultado == "ganancia":
                stats[simbolo]["g"] += 1
            elif resultado == "perdida":
                stats[simbolo]["p"] += 1

        if not stats:
            return ""

        lineas = ["WIN RATE POR ACTIVO (últimas 50 ops):"]
        for simbolo, v in stats.items():
            total = v["g"] + v["p"]
            if total > 0:
                wr = round(v["g"] / total * 100)
                lineas.append(f"  {simbolo}: {wr}% ({v['g']}G/{v['p']}P)")

        return "\n".join(lineas)

    except:
        return ""


# ============================================================
# CICLO MAESTRO
# ============================================================
async def ejecutar_ciclo_maestro() -> dict:
    inicio    = datetime.now()
    timestamp = inicio.strftime("%H:%M:%S")
    print(f"\n{'='*60}")
    print(f"[MAESTRO] Ciclo maestro iniciado: {timestamp}")
    print(f"{'='*60}")

    horario = debe_operar()
    if not horario["operar"]:
        print(f"[MAESTRO] Fuera de horario: {horario['razon']}")
        return {
            "timestamp": timestamp, "operar": False,
            "razon": horario["razon"], "decisiones": [],
            "tabla_maestra": [], "senales_fuertes": [],
            "senales_aprobadas": [], "ordenes_ejecutadas": [],
        }

    print(f"[MAESTRO] Horario: {horario.get('razon','N/A')} | Score: {horario.get('score','N/A')}/10")
    print("\n[MAESTRO] Ejecutando todos los ciclos en paralelo...")

    # Cargar historial en paralelo con los ciclos de análisis
    resultados = await asyncio.gather(
        ejecutar_ciclo_tecnico(),
        ejecutar_ciclo_avanzado(),
        ejecutar_ciclo_estrategias(),
        ejecutar_ciclo_contexto(),
        asyncio.to_thread(obtener_historial_reciente),
        asyncio.to_thread(obtener_winrate_por_activo),
        return_exceptions=True
    )

    ciclo_basico      = resultados[0] if not isinstance(resultados[0], Exception) else DEFAULTS["tecnico"]
    ciclo_avanzado    = resultados[1] if not isinstance(resultados[1], Exception) else DEFAULTS["avanzado"]
    ciclo_estrategias = resultados[2] if not isinstance(resultados[2], Exception) else DEFAULTS["estrategias"]
    ciclo_contexto    = resultados[3] if not isinstance(resultados[3], Exception) else DEFAULTS["contexto"]
    historial         = resultados[4] if not isinstance(resultados[4], Exception) else "Historial no disponible"
    winrate_activos   = resultados[5] if not isinstance(resultados[5], Exception) else ""

    for nombre, res in [("tecnico", resultados[0]), ("avanzado", resultados[1]),
                        ("estrategias", resultados[2]), ("contexto", resultados[3])]:
        if isinstance(res, Exception):
            print(f"[MAESTRO] Error en {nombre}: {res}")

    print(f"[MAESTRO] Tecnico: {len(ciclo_basico.get('senales_fuertes', []))} señales")
    print(f"[MAESTRO] Avanzado: {len(ciclo_avanzado.get('senales_fuertes', []))} señales")
    print(f"[MAESTRO] Estrategias: {len(ciclo_estrategias.get('senales_fuertes', []))} señales")
    print(f"[MAESTRO] Contexto: {ciclo_contexto.get('sesgo_contexto','N/A')} | F&G={ciclo_contexto.get('fear_greed',{}).get('valor_hoy','N/A')}")

    tabla_maestra = []
    for simbolo in ACTIVOS:
        basico     = next((t for t in ciclo_basico.get("tabla", [])           if t.get("simbolo") == simbolo), {})
        avanzado   = next((t for t in ciclo_avanzado.get("tabla", [])         if t.get("simbolo") == simbolo), {})
        estrategia = next((t for t in ciclo_estrategias.get("resultados", []) if t.get("simbolo") == simbolo), {})

        senal_basico     = basico.get("senal_final", "ESPERAR")
        senal_avanzado   = avanzado.get("senal_final", "ESPERAR")
        senal_estrategia = estrategia.get("senal_final", "ESPERAR")
        sesgo_contexto   = ciclo_contexto.get("sesgo_contexto", "NEUTRAL")
        conf_basico      = basico.get("confianza_final", 50)
        conf_avanzado    = avanzado.get("confianza", 50)
        conf_estrategia  = estrategia.get("confianza", 50)

        contexto_alineado = (
            (sesgo_contexto == "ALCISTA" and senal_basico == "COMPRAR") or
            (sesgo_contexto == "BAJISTA" and senal_basico == "VENDER") or
            sesgo_contexto == "NEUTRAL"
        )

        votos_compra = sum([
            senal_basico     == "COMPRAR",
            senal_avanzado   == "COMPRAR",
            senal_estrategia == "COMPRAR",
            contexto_alineado and sesgo_contexto == "ALCISTA",
        ])
        votos_venta = sum([
            senal_basico     == "VENDER",
            senal_avanzado   == "VENDER",
            senal_estrategia == "VENDER",
            contexto_alineado and sesgo_contexto == "BAJISTA",
        ])

        confianza_ponderada = round((conf_basico * 0.4) + (conf_avanzado * 0.3) + (conf_estrategia * 0.3))

        if votos_compra >= 3:
            senal_maestra   = "COMPRAR"
            confluencia     = "MUY_ALTA"
            confianza_final = min(confianza_ponderada + 20, 99)
        elif votos_compra >= 2:
            senal_maestra   = "COMPRAR"
            confluencia     = "ALTA"
            confianza_final = min(confianza_ponderada + 10, 99)
        elif votos_venta >= 3:
            senal_maestra   = "VENDER"
            confluencia     = "MUY_ALTA"
            confianza_final = min(confianza_ponderada + 20, 99)
        elif votos_venta >= 2:
            senal_maestra   = "VENDER"
            confluencia     = "ALTA"
            confianza_final = min(confianza_ponderada + 10, 99)
        else:
            senal_maestra   = "ESPERAR"
            confluencia     = "BAJA"
            confianza_final = max(confianza_ponderada - 20, 10)

        stop_loss    = basico.get("stop_loss", 0)
        take_profit1 = basico.get("take_profit_1", 0)
        take_profit2 = basico.get("take_profit_2", 0)
        precio       = basico.get("precio", avanzado.get("precio", 0))

        vp_val = avanzado.get("val", 0)
        vp_vah = avanzado.get("vah", 0)
        if senal_maestra == "COMPRAR" and vp_val > 0 and vp_val > stop_loss:
            stop_loss = vp_val
        elif senal_maestra == "VENDER" and vp_vah > 0 and vp_vah < stop_loss:
            stop_loss = vp_vah

        tabla_maestra.append({
            "simbolo":          simbolo,
            "precio":           precio,
            "senal_maestra":    senal_maestra,
            "confluencia":      confluencia,
            "confianza_final":  confianza_final,
            "votos_compra":     votos_compra,
            "votos_venta":      votos_venta,
            "senal_basico":     senal_basico,
            "senal_avanzado":   senal_avanzado,
            "senal_estrategia": senal_estrategia,
            "sesgo_contexto":   sesgo_contexto,
            "conf_basico":      conf_basico,
            "conf_avanzado":    conf_avanzado,
            "conf_estrategia":  conf_estrategia,
            "stop_loss":        stop_loss,
            "take_profit_1":    take_profit1,
            "take_profit_2":    take_profit2,
        })

    senales_fuertes = [
        t for t in tabla_maestra
        if t["confluencia"] in ["MUY_ALTA", "ALTA"] and t["confianza_final"] >= 80
    ]

    print(f"\n[MAESTRO] Señales fuertes: {len(senales_fuertes)}")

    senales_para_riesgo = []
    for s in senales_fuertes:
        senales_para_riesgo.append({
            "simbolo":          s["simbolo"],
            "senal_final":      s["senal_maestra"],
            "senal_basico":     s["senal_basico"],
            "senal_avanzado":   s["senal_avanzado"],
            "senal_estrategia": s["senal_estrategia"],
            "sesgo_contexto":   s["sesgo_contexto"],
            "precio":           s["precio"],
            "stop_loss":        s["stop_loss"],
            "take_profit_1":    s["take_profit_1"],
            "take_profit_2":    s["take_profit_2"],
            "confianza_final":  s["confianza_final"],
            "confluencia":      s["confluencia"],
        })

    resultado_riesgo  = await ejecutar_digestor_riesgo(
        senales_para_riesgo,
        sesgo_contexto=ciclo_contexto.get("sesgo_contexto", "NEUTRAL")
    )
    senales_aprobadas = resultado_riesgo.get("senales_aprobadas", [])

    resumen_tabla = "\n".join([
        f"{t['simbolo']}: {t['senal_maestra']} | conf={t['confianza_final']}% | {t['confluencia']} | "
        f"votos C={t['votos_compra']} V={t['votos_venta']} | "
        f"tecnico={t['senal_basico']} avanzado={t['senal_avanzado']} "
        f"estrategia={t['senal_estrategia']} contexto={t['sesgo_contexto']} | "
        f"precio={t['precio']} SL={t['stop_loss']} TP1={t['take_profit_1']} TP2={t['take_profit_2']}"
        for t in tabla_maestra
    ]) if tabla_maestra else "Sin datos disponibles"

    resumen_contexto = f"""
CONTEXTO GLOBAL:
Fear & Greed: {ciclo_contexto.get('fear_greed',{}).get('valor_hoy','N/A')} ({ciclo_contexto.get('fear_greed',{}).get('clasificacion','N/A')})
Sesgo mercado: {ciclo_contexto.get('sesgo_contexto','N/A')} | Confianza: {ciclo_contexto.get('confianza_contexto','N/A')}%
WTI Petroleo: ${ciclo_contexto.get('wti_precio','N/A')} ({ciclo_contexto.get('wti_cambio','N/A')}% hoy)
Analisis: {ciclo_contexto.get('analisis_consolidado','Sin datos')[:300]}
"""

    # Contexto histórico — lo que el sistema ha aprendido hoy
    resumen_historico = f"""
{historial}

{winrate_activos}
"""

    print("[MAESTRO] Generando decision maestra con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": (
            f"TABLA MAESTRA:\n{resumen_tabla}\n\n"
            f"{resumen_contexto}\n\n"
            f"SEÑALES APROBADAS POR RIESGO: {len(senales_aprobadas)}\n\n"
            f"{resumen_historico}"
        )}],
        system=(
            "Eres el cerebro maestro de un sistema de trading algoritmico profesional. "
            "Recibes analisis de 4 sistemas: "
            "1.TECNICO BASICO: velas+indicadores+orderflow+niveles+onchain "
            "2.TECNICO AVANZADO: funding+liquidaciones+estructura+volume_profile "
            "3.ESTRATEGIAS: ORB+VWAP+Gap+MeanReversion+NewsMomentum+VIX+Arbitraje "
            "4.CONTEXTO: sentimiento+macro+fundamental+historico+petroleo+trends+estacionalidad+opciones. "
            "Tambien recibes el HISTORIAL RECIENTE de señales del dia y el WIN RATE por activo. "
            "Usa el historial para aprender: si un activo tiene win rate bajo hoy, sube el umbral de confianza requerido. "
            "Si el win rate es alto, puedes ser mas agresivo. "
            "Prioriza señales donde al menos 3 sistemas coinciden. "
            "El contexto actua como filtro — mercado bajista evita compras. "
            "Entrega SOLO decisiones con confluencia MUY_ALTA o ALTA y confianza MAYOR A 80%. "
            "Formato estricto:\n"
            "DECISION_MAESTRA_N:\n"
            "- ACCION: COMPRAR o VENDER\n"
            "- SIMBOLO: nombre\n"
            "- PRECIO_ENTRADA: numero\n"
            "- STOP_LOSS: numero\n"
            "- TAKE_PROFIT_1: numero (ratio minimo 2:1)\n"
            "- TAKE_PROFIT_2: numero (ratio minimo 3:1)\n"
            "- CONFIANZA_SISTEMA: porcentaje\n"
            "- SISTEMAS_CONFIRMACION: cuales sistemas confirman\n"
            "- RAZON_MAESTRA: dos oraciones con niveles especificos\n"
            "- HORIZONTE: timeframe\n"
            "- PRIORIDAD: 1 a 3\n"
            "Si no hay señales: SISTEMA_EN_ESPERA. Responde en español sin texto adicional."
        ),
        max_tokens=1000,
        agente="digestor_maestro"
    )

    duracion = (datetime.now() - inicio).total_seconds()
    stats    = obtener_estadisticas_dia()

    log_ciclo(
        ciclo_num=stats.get("total_ordenes", 0) + 1,
        señales_detectadas=len(senales_fuertes),
        ordenes_ejecutadas=len(senales_aprobadas),
        duracion_segundos=duracion,
        modelo_usado=respuesta.get("modelo", "N/A")
    )

    from agente_financiero.ejecutor_alpaca import ejecutar_orden
    ordenes_ejecutadas = []
    for senal in senales_aprobadas:
        t = senal.get("tamano_posicion", {})
        if t.get("cantidad", 0) > 0:
            orden = ejecutar_orden(
                simbolo=senal["simbolo"],
                accion=senal["accion"],
                cantidad=t["cantidad"],
                precio_entrada=senal.get("precio", 0),
                stop_loss=senal.get("stop_loss", 0),
                take_profit=senal.get("take_profit_1", 0),
                atr=senal.get("atr_pct", 0)
            )
            ordenes_ejecutadas.append(orden)
            print(f"[MAESTRO] Orden ejecutada: {senal['simbolo']} {senal['accion']}")

    return {
        "timestamp":          timestamp,
        "operar":             True,
        "duracion_segundos":  round(duracion, 1),
        "horario":            horario,
        "tabla_maestra":      tabla_maestra,
        "senales_fuertes":    senales_fuertes,
        "senales_aprobadas":  senales_aprobadas,
        "ordenes_ejecutadas": ordenes_ejecutadas,
        "decision_maestra":   respuesta["texto"],
        "modelo":             respuesta["modelo"],
        "estadisticas_dia":   stats,
    }
