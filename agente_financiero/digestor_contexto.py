# agente_financiero/digestor_contexto.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from nucleo.cliente_ia import chat
from agente_financiero.agente_sentimiento import analizar_sentimiento_mercado
from agente_financiero.agente_macro import analizar_contexto_macro
from agente_financiero.agente_fundamental import analizar_fundamental_completo
from agente_financiero.agente_historico import analizar_historico_completo
from agente_financiero.agente_petroleo import analizar_petroleo_completo
from agente_financiero.agente_google_trends import ejecutar_google_trends
from agente_financiero.agente_estacionalidad import analizar_estacionalidad_completo
from agente_financiero.agente_opciones import analizar_opciones_completo

# Cache para Google Trends — no bloquea el ciclo si ya tiene datos
_trends_cache     = []
_trends_cache_ts  = 0

async def obtener_trends_con_timeout(timeout: int = 60) -> list:
    global _trends_cache, _trends_cache_ts
    import time
    ahora = time.time()

    # Si hay cache menor a 1 hora lo usa directamente
    if _trends_cache and (ahora - _trends_cache_ts) < 3600:
        print("[digestor_contexto] Trends: usando cache")
        return _trends_cache

    try:
        resultado = await asyncio.wait_for(
            asyncio.to_thread(ejecutar_google_trends),
            timeout=timeout
        )
        _trends_cache    = resultado
        _trends_cache_ts = time.time()
        return resultado
    except asyncio.TimeoutError:
        print(f"[digestor_contexto] Trends: timeout {timeout}s — usando cache anterior")
        return _trends_cache or []
    except Exception as e:
        print(f"[digestor_contexto] Trends: error — {e}")
        return _trends_cache or []

async def ejecutar_ciclo_contexto() -> dict:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[digestor_contexto] Ciclo contexto {timestamp}")

    print("[1/8] Ejecutando 7 agentes en paralelo + trends con timeout...")

    # Los 7 agentes rapidos corren en paralelo
    # Trends corre con timeout de 60s para no bloquear
    resultados = await asyncio.gather(
        analizar_sentimiento_mercado(),
        analizar_contexto_macro(),
        analizar_fundamental_completo(),
        analizar_historico_completo(),
        analizar_petroleo_completo(),
        asyncio.to_thread(analizar_estacionalidad_completo),
        asyncio.to_thread(analizar_opciones_completo),
        obtener_trends_con_timeout(timeout=60),
    )

    sent_res, macro_res, fund_res, hist_res, petro_res, estac_res, opciones_res, trends_res = resultados

    # Fear & Greed
    fear_greed   = sent_res.get("fear_greed", {})
    fg_valor     = fear_greed.get("valor_hoy", 50)
    fg_clasif    = fear_greed.get("clasificacion", "Neutral")
    fg_tendencia = fear_greed.get("tendencia", "neutral")

    # Analisis textuales
    sent_analisis  = sent_res.get("analisis", "Sin datos")
    macro_analisis = macro_res.get("analisis", "Sin datos")
    fund_analisis  = fund_res.get("analisis", "Sin datos")
    hist_analisis  = hist_res.get("analisis", "Sin datos")
    petro_analisis = petro_res.get("analisis", "Sin datos")
    wti_precio     = petro_res.get("precios", {}).get("WTI", {}).get("precio", "N/A")
    wti_cambio     = petro_res.get("precios", {}).get("WTI", {}).get("cambio_dia", 0)

    # Estacionalidad y opciones
    estac_señal    = estac_res.get("señal_estacional", "NEUTRAL")
    estac_conf     = estac_res.get("confianza", 50)
    estac_fase     = estac_res.get("ciclo_halving", {}).get("fase", "N/A")
    opciones_btc   = next((o for o in opciones_res if o.get("moneda") == "BTC"), {})
    pcr_btc        = opciones_btc.get("pcr_volumen", 1.0)
    maxpain_btc    = opciones_btc.get("max_pain", "N/A")
    opciones_señal = opciones_btc.get("señal", "ESPERAR")

    print(f"[digestor_contexto] F&G={fg_valor} | Estac={estac_señal} | PCR={pcr_btc} | WTI=${wti_precio}")

    # Google Trends
    trends_señales = [t for t in trends_res if t.get("señal") not in ["ESPERAR", None] and not t.get("error")]
    trends_resumen = "\n".join([
        f"{t['simbolo']}: {t['señal']} | valor={t['valor_actual']} vs prom={t['promedio_3m']} | {t['razon']}"
        for t in trends_señales
    ]) if trends_señales else "Sin señales de trends disponibles"
    print(f"[digestor_contexto] Trends: {len(trends_señales)} señales")

    # Sesgo de contexto
    puntos_alcista = 0
    puntos_bajista = 0

    if fg_valor > 60:   puntos_alcista += 2
    elif fg_valor > 50: puntos_alcista += 1
    elif fg_valor < 40: puntos_bajista += 2
    elif fg_valor < 50: puntos_bajista += 1

    if fg_tendencia == "mejorando": puntos_alcista += 1
    else:                           puntos_bajista += 1

    if wti_cambio > 2:   puntos_bajista += 1
    elif wti_cambio < -2: puntos_alcista += 1

    if "BAJISTA" in estac_señal:  puntos_bajista += 2
    elif "ALCISTA" in estac_señal: puntos_alcista += 2

    if opciones_señal == "COMPRAR": puntos_alcista += 1
    elif opciones_señal == "VENDER": puntos_bajista += 1

    # Trends suma 1 punto si hay señal clara
    if len(trends_señales) >= 3:
        compra_trends = sum(1 for t in trends_señales if t.get("señal") == "COMPRAR")
        venta_trends  = sum(1 for t in trends_señales if t.get("señal") == "VENDER")
        if compra_trends > venta_trends: puntos_alcista += 1
        elif venta_trends > compra_trends: puntos_bajista += 1

    if puntos_alcista > puntos_bajista:
        sesgo_contexto     = "ALCISTA"
        confianza_contexto = min(50 + puntos_alcista * 10, 85)
    elif puntos_bajista > puntos_alcista:
        sesgo_contexto     = "BAJISTA"
        confianza_contexto = min(50 + puntos_bajista * 10, 85)
    else:
        sesgo_contexto     = "NEUTRAL"
        confianza_contexto = 50

    print(f"[digestor_contexto] Sesgo={sesgo_contexto} | Confianza={confianza_contexto}%")

    contexto_completo = f"""
SENTIMIENTO:
Fear & Greed: {fg_valor} ({fg_clasif}) — tendencia {fg_tendencia}
{sent_analisis[:300]}

MACRO:
{macro_analisis[:300]}

FUNDAMENTAL:
{fund_analisis[:200]}

HISTORICO:
{hist_analisis[:200]}

PETROLEO:
WTI=${wti_precio} ({wti_cambio}% hoy)
{petro_analisis[:200]}

GOOGLE TRENDS:
{trends_resumen}

ESTACIONALIDAD:
{estac_señal} ({estac_conf}%) — Fase halving: {estac_fase}

OPCIONES:
BTC PCR={pcr_btc} | MaxPain=${maxpain_btc} | Señal={opciones_señal}

SESGO CALCULADO: {sesgo_contexto} ({confianza_contexto}%)
"""

    print("[digestor_contexto] Generando analisis consolidado con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"Consolida este contexto:\n{contexto_completo}"}],
        system="""Eres el digestor de contexto de mercado.
Entrega reporte ejecutivo con:
1. Sesgo general (alcista/bajista/neutral) con confianza
2. Factores macro mas importantes
3. Nivel de riesgo: BAJO/MEDIO/ALTO
4. Recomendacion para proximas 24 horas
Responde en español, maximo 200 palabras.""",
        max_tokens=400
    )

    return {
        "timestamp":            timestamp,
        "fear_greed":           fear_greed,
        "sesgo_contexto":       sesgo_contexto,
        "confianza_contexto":   confianza_contexto,
        "wti_precio":           wti_precio,
        "wti_cambio":           wti_cambio,
        "estac_señal":          estac_señal,
        "pcr_btc":              pcr_btc,
        "maxpain_btc":          maxpain_btc,
        "analisis_consolidado": respuesta["texto"],
        "modelo":               respuesta["modelo"],
        "fuentes": {
            "sentimiento": sent_analisis[:200],
            "macro":       macro_analisis[:200],
            "fundamental": fund_analisis[:200],
            "historico":   hist_analisis[:200],
            "petroleo":    petro_analisis[:200],
        }
    }