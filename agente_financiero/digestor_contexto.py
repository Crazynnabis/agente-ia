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

async def ejecutar_ciclo_contexto() -> dict:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[digestor_contexto] Ciclo contexto {timestamp}")

    print("[1/8] Todos los contextos en paralelo...")
    sent_res, macro_res, fund_res, hist_res, petro_res, trends_res, estac_res, opciones_res = await asyncio.gather(
        analizar_sentimiento_mercado(),
        analizar_contexto_macro(),
        analizar_fundamental_completo(),
        analizar_historico_completo(),
        analizar_petroleo_completo(),
        asyncio.to_thread(ejecutar_google_trends),
        asyncio.to_thread(analizar_estacionalidad_completo),
        asyncio.to_thread(analizar_opciones_completo),
    )

    # Extrae datos de estacionalidad y opciones
    estac_señal   = estac_res.get("señal_estacional", "NEUTRAL")
    estac_conf    = estac_res.get("confianza", 50)
    estac_fase    = estac_res.get("ciclo_halving", {}).get("fase", "N/A")
    opciones_btc  = next((o for o in opciones_res if o.get("moneda") == "BTC"), {})
    pcr_btc       = opciones_btc.get("pcr_volumen", 1.0)
    maxpain_btc   = opciones_btc.get("max_pain", "N/A")
    opciones_señal= opciones_btc.get("señal", "ESPERAR")

    print(f"[digestor_contexto] Estacionalidad: {estac_señal} ({estac_conf}%) — {estac_fase}")
    print(f"[digestor_contexto] Opciones BTC PCR={pcr_btc} MaxPain=${maxpain_btc} señal={opciones_señal}")

    # Ajusta puntos con estacionalidad y opciones
    if "BAJISTA" in estac_señal:
        puntos_bajista += 2
    elif "ALCISTA" in estac_señal:
        puntos_alcista += 2

    if opciones_señal == "COMPRAR":
        puntos_alcista += 1
    elif opciones_señal == "VENDER":
        puntos_bajista += 1

    # Señales de Google Trends
    trends_señales = [t for t in trends_res if t.get("señal") not in ["ESPERAR", None]]
    trends_resumen = "\n".join([
        f"{t['simbolo']}: {t['señal']} | valor={t['valor_actual']} vs prom={t['promedio_3m']} | {t['razon']}"
        for t in trends_señales
    ]) if trends_señales else "Sin señales de trends"
    print(f"[digestor_contexto] Trends: {len(trends_señales)} señales")

    # Extrae señales clave de cada fuente
    fear_greed    = sent_res.get("fear_greed", {})
    fg_valor      = fear_greed.get("valor_hoy", 50)
    fg_clasif     = fear_greed.get("clasificacion", "Neutral")
    fg_tendencia  = fear_greed.get("tendencia", "neutral")

    sent_analisis  = sent_res.get("analisis", "Sin datos")
    macro_analisis = macro_res.get("analisis", "Sin datos")
    fund_analisis  = fund_res.get("analisis", "Sin datos")
    hist_analisis  = hist_res.get("analisis", "Sin datos")
    petro_analisis = petro_res.get("analisis", "Sin datos")
    wti_precio     = petro_res.get("precios", {}).get("WTI", {}).get("precio", "N/A")
    wti_cambio     = petro_res.get("precios", {}).get("WTI", {}).get("cambio_dia", 0)

    # Determina sesgo de contexto
    puntos_alcista = 0
    puntos_bajista = 0

    if fg_valor > 60:
        puntos_alcista += 2
    elif fg_valor > 50:
        puntos_alcista += 1
    elif fg_valor < 40:
        puntos_bajista += 2
    elif fg_valor < 50:
        puntos_bajista += 1

    if fg_tendencia == "mejorando":
        puntos_alcista += 1
    else:
        puntos_bajista += 1

    if wti_cambio > 2:
        puntos_bajista += 1  # petroleo caro presiona mercados
    elif wti_cambio < -2:
        puntos_alcista += 1  # petroleo barato favorece economia

    if puntos_alcista > puntos_bajista:
        sesgo_contexto = "ALCISTA"
        confianza_contexto = min(50 + puntos_alcista * 10, 85)
    elif puntos_bajista > puntos_alcista:
        sesgo_contexto = "BAJISTA"
        confianza_contexto = min(50 + puntos_bajista * 10, 85)
    else:
        sesgo_contexto = "NEUTRAL"
        confianza_contexto = 50

    # Resumen consolidado para IA
    contexto_completo = f"""
SENTIMIENTO DE MERCADO:
Fear & Greed: {fg_valor} ({fg_clasif}) — tendencia {fg_tendencia}
{sent_analisis[:400]}

CONTEXTO MACRO:
{macro_analisis[:400]}

FUNDAMENTAL:
{fund_analisis[:300]}

HISTORICO:
{hist_analisis[:300]}

PETROLEO:
WTI=${wti_precio} ({wti_cambio}% hoy)
{petro_analisis[:300]}

GOOGLE TRENDS:
{trends_resumen}

ESTACIONALIDAD:
{estac_señal} ({estac_conf}%) — Fase halving: {estac_fase}
{estac_res.get('razon_mes','')} | {estac_res.get('razon_halving','')}

OPCIONES (Put/Call Ratio):
BTC PCR={pcr_btc} | MaxPain=${maxpain_btc} | Señal={opciones_señal}
"""

    print("[digestor_contexto] Generando analisis consolidado con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"Consolida este contexto de mercado:\n{contexto_completo}"}],
        system="""Eres el digestor de contexto de mercado. Recibes datos de sentimiento, macro, fundamental, historico y petroleo.
Entrega un reporte ejecutivo con:
1. Sesgo general del mercado (alcista/bajista/neutral) con nivel de confianza
2. Factores macro mas importantes ahora mismo
3. Sectores favorecidos y perjudicados
4. Nivel de riesgo global: BAJO/MEDIO/ALTO
5. Recomendacion estrategica para las proximas 24 horas
Responde en español, conciso y accionable. Maximo 300 palabras.""",
        max_tokens=500
    )

    return {
        "timestamp":          timestamp,
        "fear_greed":         fear_greed,
        "sesgo_contexto":     sesgo_contexto,
        "confianza_contexto": confianza_contexto,
        "wti_precio":         wti_precio,
        "wti_cambio":         wti_cambio,
        "analisis_consolidado": respuesta["texto"],
        "modelo":             respuesta["modelo"],
        "fuentes": {
            "sentimiento":  sent_analisis[:200],
            "macro":        macro_analisis[:200],
            "fundamental":  fund_analisis[:200],
            "historico":    hist_analisis[:200],
            "petroleo":     petro_analisis[:200],
        }
    }