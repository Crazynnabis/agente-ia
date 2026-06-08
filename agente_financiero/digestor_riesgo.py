# agente_financiero/digestor_riesgo.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from nucleo.cliente_ia import chat
from agente_financiero.gestion_riesgo import GestorRiesgo
from agente_financiero.filtro_tendencia import filtrar_señal_por_tendencia
from agente_financiero.horario_trading import debe_operar
from agente_financiero.logger_trading import log_senal, obtener_estadisticas_dia
from agente_financiero.agente_calendario import analizar_calendario

gestor = GestorRiesgo()

async def procesar_senal(senal: dict) -> dict:
    simbolo = senal.get("simbolo", "")
    accion  = senal.get("senal_final", "ESPERAR")
    precio  = senal.get("precio", 0)
    sl      = senal.get("stop_loss", 0)
    tp1     = senal.get("take_profit_1", 0)
    tp2     = senal.get("take_profit_2", 0)

    resultado = {
        "simbolo":         simbolo,
        "accion":          accion,
        "precio":          precio,
        "aprobada_final":  False,
        "razones_rechazo": [],
        "warnings":        [],
        "tamano_posicion": {},
        "tendencia":       {},
        "horario":         {},
        "riesgo":          {},
    }

    horario = debe_operar()
    resultado["horario"] = horario
    if not horario["operar"]:
        resultado["razones_rechazo"].append(horario["razon"])

    filtro = filtrar_señal_por_tendencia(senal)
    resultado["tendencia"] = filtro
    if not filtro["aprobada"]:
        resultado["razones_rechazo"].append(filtro["razon"])

    validacion = gestor.validar_senal(senal)
    resultado["riesgo"]          = validacion
    resultado["tamano_posicion"] = validacion.get("tamano", {})
    if not validacion["aprobada"]:
        resultado["razones_rechazo"].extend(validacion["errores"])
    resultado["warnings"].extend(validacion.get("warnings", []))

    resultado["aprobada_final"] = len(resultado["razones_rechazo"]) == 0

    fuentes_confirmacion = []
    if senal.get("senal_basico")     != "ESPERAR": fuentes_confirmacion.append("tecnico")
    if senal.get("senal_avanzado")   != "ESPERAR": fuentes_confirmacion.append("avanzado")
    if senal.get("senal_estrategia") != "ESPERAR": fuentes_confirmacion.append("estrategias")
    if senal.get("sesgo_contexto")   != "NEUTRAL":  fuentes_confirmacion.append("contexto")
    if not fuentes_confirmacion:
        fuentes_confirmacion = ["tecnico"]

    log_senal(
        simbolo=simbolo,
        accion=accion,
        precio=precio,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        confianza=senal.get("confianza_final", 0),
        fuentes=fuentes_confirmacion,
        razon=senal.get("razon", ""),
        horizonte=senal.get("horizonte", "15min"),
        aprobada_riesgo=validacion["aprobada"],
        aprobada_tendencia=filtro["aprobada"],
        tamano_posicion=resultado["tamano_posicion"],
    )

    return resultado


def _obtener_contexto_mercado() -> str:
    """Obtiene contexto actual del mercado para el prompt de riesgo."""
    try:
        from loop_automatico import get_estado
        fg          = get_estado("fear_greed") or 50
        sesgo       = get_estado("sesgo_contexto") or "NEUTRAL"
        vol_alta    = get_estado("volatilidad_alta") or False
        pcr         = get_estado("pcr_btc") or 1.0
        conservador = get_estado("modo_conservador") or False
        ballenas    = get_estado("ballenas_senal") or "ESPERAR"
        dxy         = get_estado("dxy_senal") or "ESPERAR"

        # Nivel de riesgo calculado
        if fg < 20 or vol_alta:
            nivel_riesgo = "EXTREMO — reducir tamaños al mínimo"
        elif fg < 35 or conservador:
            nivel_riesgo = "ALTO — operar con cautela"
        elif fg > 75:
            nivel_riesgo = "ALTO — mercado sobrecomprado"
        else:
            nivel_riesgo = "NORMAL"

        return (
            f"CONTEXTO DE MERCADO ACTUAL:\n"
            f"Fear & Greed: {fg}/100\n"
            f"Sesgo general: {sesgo}\n"
            f"Volatilidad alta: {'SÍ' if vol_alta else 'No'}\n"
            f"Modo conservador: {'SÍ' if conservador else 'No'}\n"
            f"PCR BTC: {pcr}\n"
            f"Ballenas: {ballenas}\n"
            f"DXY señal: {dxy}\n"
            f"Nivel de riesgo calculado: {nivel_riesgo}"
        )
    except:
        return "CONTEXTO: No disponible — usar criterio conservador"


async def ejecutar_digestor_riesgo(senales: list, sesgo_contexto: str = "NEUTRAL") -> dict:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[digestor_riesgo] Procesando {len(senales)} señales...")

    horario = debe_operar()
    if not horario["operar"]:
        print(f"[digestor_riesgo] Fuera de horario: {horario['razon']}")
        return {
            "timestamp":          timestamp,
            "operar":             False,
            "razon":              horario["razon"],
            "senales_aprobadas":  [],
            "senales_rechazadas": senales,
        }

    calendario = analizar_calendario()
    if calendario["debe_pausar"]:
        print(f"[digestor_riesgo] PAUSA por calendario: {calendario['razon_pausa']}")
        try:
            from agente_financiero.alertas_telegram import enviar_mensaje
            enviar_mensaje(f"⏸ Trading pausado\n{calendario['razon_pausa']}")
        except:
            pass
        return {
            "timestamp":          timestamp,
            "operar":             False,
            "razon":              calendario["razon_pausa"],
            "senales_aprobadas":  [],
            "senales_rechazadas": senales,
        }

    senales_aprobadas  = []
    senales_rechazadas = []

    for senal in senales:
        if senal.get("senal_final") == "ESPERAR":
            continue

        print(f"[digestor_riesgo] Procesando {senal.get('simbolo')}...")

        accion = senal.get("senal_final", "ESPERAR")
        if sesgo_contexto == "BAJISTA" and accion == "COMPRAR":
            print(f"  RECHAZADA por contexto BAJISTA")
            senales_rechazadas.append({
                "simbolo": senal.get("simbolo"),
                "razones_rechazo": ["Contexto macro BAJISTA — evitar compras"]
            })
            continue
        elif sesgo_contexto == "ALCISTA" and accion == "VENDER":
            print(f"  RECHAZADA por contexto ALCISTA")
            senales_rechazadas.append({
                "simbolo": senal.get("simbolo"),
                "razones_rechazo": ["Contexto macro ALCISTA — evitar ventas"]
            })
            continue

        resultado = await procesar_senal(senal)

        if resultado["aprobada_final"]:
            senales_aprobadas.append(resultado)
            print(f"  APROBADA: {senal.get('simbolo')} {senal.get('senal_final')}")
        else:
            senales_rechazadas.append(resultado)
            razones = ', '.join(resultado['razones_rechazo'])
            print(f"  RECHAZADA: {razones}")

    max_ops = horario.get("max_operaciones", 2)
    if len(senales_aprobadas) > max_ops:
        senales_aprobadas = sorted(
            senales_aprobadas,
            key=lambda x: x.get("riesgo", {}).get("tamano", {}).get("cantidad", 0),
            reverse=True
        )[:max_ops]
        print(f"[digestor_riesgo] Limitado a {max_ops} operaciones por horario")

    # ── Evaluación IA con contexto real de mercado ────────────
    if senales_aprobadas:
        stats          = obtener_estadisticas_dia()
        contexto_mkt   = _obtener_contexto_mercado()

        resumen_senales = "\n".join([
            f"{s['simbolo']}: {s['accion']} @ {s['precio']} | "
            f"conf={s.get('riesgo',{}).get('tamano',{}).get('distancia_sl_pct','N/A')}% SL | "
            f"tamaño=${s.get('tamano_posicion',{}).get('valor_posicion_usd','N/A')} | "
            f"riesgo=${s.get('tamano_posicion',{}).get('riesgo_usd','N/A')}"
            for s in senales_aprobadas
        ])

        resumen_dia = (
            f"Operaciones hoy: {stats.get('total_ordenes', 0)} | "
            f"Win rate: {stats.get('win_rate', 0):.0f}% | "
            f"P&L día: ${stats.get('pnl_total_usd', 0):+,.0f}"
        )

        respuesta = await chat(
            mensajes=[{"role": "user", "content": (
                f"SEÑALES APROBADAS POR FILTROS NUMÉRICOS:\n{resumen_senales}\n\n"
                f"{contexto_mkt}\n\n"
                f"ESTADÍSTICAS DEL DÍA: {resumen_dia}\n\n"
                f"Evalúa si estas señales son prudentes dado el contexto actual."
            )}],
            system=(
                "Eres el gestor de riesgo de un sistema de trading algorítmico. "
                "Tu función es la aprobación final antes de ejecutar órdenes reales.\n\n"
                "Analiza cada señal considerando:\n"
                "1. El contexto de mercado actual (Fear & Greed, volatilidad, sesgo)\n"
                "2. Si el tamaño de posición es adecuado al riesgo actual\n"
                "3. Si el momento del día y las condiciones son favorables\n"
                "4. El rendimiento del día (no operar si el win rate es muy bajo)\n\n"
                "Responde en este formato exacto:\n"
                "EVALUACION_RIESGO:\n"
                "- CONTEXTO: descripcion del riesgo actual en una oracion\n"
                "- RECOMENDACION: EJECUTAR o ESPERAR\n"
                "- RAZON: una oracion explicando la decision\n"
                "- AJUSTE_TAMAÑO: NORMAL, REDUCIR_50PCT o REDUCIR_75PCT\n\n"
                "Sé conservador — si hay duda, recomienda ESPERAR. "
                "Responde en español sin texto adicional."
            ),
            max_tokens=200,
            agente="digestor_riesgo"
        )
        confirmacion = respuesta["texto"]

        # Aplicar ajuste de tamaño si Claude lo recomienda
        if "REDUCIR_50PCT" in confirmacion:
            for s in senales_aprobadas:
                if "tamano_posicion" in s and "cantidad" in s["tamano_posicion"]:
                    s["tamano_posicion"]["cantidad"] = round(
                        s["tamano_posicion"]["cantidad"] * 0.5, 6
                    )
                    s["tamano_posicion"]["valor_posicion_usd"] = round(
                        s["tamano_posicion"].get("valor_posicion_usd", 0) * 0.5, 2
                    )
            print(f"[digestor_riesgo] Tamaño reducido 50% por recomendación IA")

        elif "REDUCIR_75PCT" in confirmacion:
            for s in senales_aprobadas:
                if "tamano_posicion" in s and "cantidad" in s["tamano_posicion"]:
                    s["tamano_posicion"]["cantidad"] = round(
                        s["tamano_posicion"]["cantidad"] * 0.25, 6
                    )
                    s["tamano_posicion"]["valor_posicion_usd"] = round(
                        s["tamano_posicion"].get("valor_posicion_usd", 0) * 0.25, 2
                    )
            print(f"[digestor_riesgo] Tamaño reducido 75% por recomendación IA")

        elif "ESPERAR" in confirmacion and "RECOMENDACION: ESPERAR" in confirmacion:
            print(f"[digestor_riesgo] IA recomienda ESPERAR — señales bloqueadas")
            senales_rechazadas.extend(senales_aprobadas)
            senales_aprobadas = []

    else:
        confirmacion = "Ninguna señal pasó todos los filtros de riesgo."

    stats = obtener_estadisticas_dia()

    return {
        "timestamp":          timestamp,
        "operar":             True,
        "horario":            horario,
        "senales_aprobadas":  senales_aprobadas,
        "senales_rechazadas": senales_rechazadas,
        "confirmacion_ia":    confirmacion,
        "estadisticas_dia":   stats,
    }
