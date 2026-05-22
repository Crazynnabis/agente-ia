# agente_financiero/agente_google_trends.py
# Reemplaza Google Trends con CoinGecko — sin bloqueos, gratis, más relevante
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import requests
import time
from datetime import datetime

# Cache global — 4 horas
_cache_trends = {}
_cache_ts     = {}
TTL_TRENDS    = 14400  # 4 horas

# Mapeo de símbolos a IDs de CoinGecko
COINGECKO_MAP = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "SOLUSDT": "solana",
    "BNBUSDT": "binancecoin",
}

HEADERS = {"accept": "application/json"}

def obtener_datos_coingecko(coin_id: str) -> dict:
    """Obtiene datos de mercado, tendencias y sentimiento de CoinGecko."""
    try:
        # Datos de mercado — precio, volumen, cambios, sentiment
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        params = {
            "localization":          "false",
            "tickers":               "false",
            "market_data":           "true",
            "community_data":        "true",
            "developer_data":        "false",
            "sparkline":             "false",
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if r.status_code == 429:
            print(f"[agente_trends] CoinGecko rate limit — usando cache")
            return {}
        if r.status_code != 200:
            return {}
        return r.json()
    except Exception as e:
        print(f"[agente_trends] Error CoinGecko {coin_id}: {e}")
        return {}

def obtener_trending_coingecko() -> list:
    """Obtiene las monedas trending en CoinGecko en las últimas 24h."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/search/trending",
            headers=HEADERS, timeout=10
        )
        if r.status_code != 200:
            return []
        data  = r.json()
        coins = data.get("coins", [])
        return [c["item"]["id"] for c in coins]
    except:
        return []

def analizar_tendencia_activo(simbolo: str) -> dict:
    """
    Analiza tendencia de un activo usando CoinGecko.
    Misma interfaz que Google Trends para compatibilidad.
    """
    coin_id = COINGECKO_MAP.get(simbolo)
    if not coin_id:
        return {
            "simbolo": simbolo, "señal": "ESPERAR",
            "fuerza": "baja", "razon": "Sin mapeo CoinGecko",
            "error": True,
        }

    print(f"[agente_trends] Analizando {simbolo} via CoinGecko...")

    # Cache hit
    ahora = time.time()
    if simbolo in _cache_trends and (ahora - _cache_ts.get(simbolo, 0)) < TTL_TRENDS:
        print(f"[agente_trends] Cache hit {simbolo}")
        return _cache_trends[simbolo]

    datos = obtener_datos_coingecko(coin_id)
    if not datos:
        # Devuelve cache anterior si existe
        if simbolo in _cache_trends:
            print(f"[agente_trends] Sin datos nuevos — usando cache anterior {simbolo}")
            return _cache_trends[simbolo]
        return {
            "simbolo": simbolo, "señal": "ESPERAR",
            "fuerza": "baja", "razon": "Sin datos CoinGecko",
            "promedio": 0, "valor_actual": 0,
            "error": True,
        }

    # Extrae métricas de mercado
    market      = datos.get("market_data", {})
    community   = datos.get("community_data", {})
    sentiment   = datos.get("sentiment_votes_up_percentage", 50) or 50

    cambio_1h   = market.get("price_change_percentage_1h_in_currency",  {}).get("usd", 0) or 0
    cambio_24h  = market.get("price_change_percentage_24h_in_currency", {}).get("usd", 0) or 0
    cambio_7d   = market.get("price_change_percentage_7d_in_currency",  {}).get("usd", 0) or 0
    volumen_24h = market.get("total_volume",    {}).get("usd", 0) or 0
    vol_cambio  = market.get("market_cap_change_percentage_24h", 0) or 0
    precio      = market.get("current_price",   {}).get("usd", 0) or 0
    ath_pct     = market.get("ath_change_percentage", {}).get("usd", 0) or 0

    # Reddit / community como proxy de interés
    reddit_subs     = community.get("reddit_subscribers", 0) or 0
    twitter_follows = community.get("twitter_followers",  0) or 0

    # Verifica si está en trending
    trending_ids = obtener_trending_coingecko()
    en_trending  = coin_id in trending_ids

    # ── Lógica de señal ──────────────────────────────────────
    puntos_compra = 0
    puntos_venta  = 0
    razones       = []

    # Momentum de precio
    if cambio_1h > 1.5:
        puntos_compra += 2
        razones.append(f"momentum 1h +{cambio_1h:.1f}%")
    elif cambio_1h < -1.5:
        puntos_venta += 2
        razones.append(f"momentum 1h {cambio_1h:.1f}%")

    if cambio_24h > 3:
        puntos_compra += 2
        razones.append(f"sube {cambio_24h:.1f}% en 24h")
    elif cambio_24h < -3:
        puntos_venta += 2
        razones.append(f"cae {cambio_24h:.1f}% en 24h")

    if cambio_7d > 10:
        puntos_compra += 1
        razones.append(f"tendencia 7d +{cambio_7d:.1f}%")
    elif cambio_7d < -10:
        puntos_venta += 1
        razones.append(f"tendencia 7d {cambio_7d:.1f}%")

    # Sentimiento de la comunidad
    if sentiment > 70:
        puntos_compra += 1
        razones.append(f"sentimiento alcista {sentiment:.0f}%")
    elif sentiment < 35:
        puntos_venta += 1
        razones.append(f"sentimiento bajista {sentiment:.0f}%")

    # Trending en CoinGecko
    if en_trending:
        puntos_compra += 2
        razones.append("en trending CoinGecko")

    # Volumen anormal
    if vol_cambio > 20:
        puntos_compra += 1
        razones.append(f"volumen cap +{vol_cambio:.1f}%")
    elif vol_cambio < -20:
        puntos_venta += 1
        razones.append(f"volumen cap {vol_cambio:.1f}%")

    # ── Determina señal final ────────────────────────────────
    if puntos_compra >= 4:
        señal  = "COMPRAR"
        fuerza = "alta"
    elif puntos_compra >= 2:
        señal  = "COMPRAR"
        fuerza = "media"
    elif puntos_venta >= 4:
        señal  = "VENDER"
        fuerza = "alta"
    elif puntos_venta >= 2:
        señal  = "VENDER"
        fuerza = "media"
    else:
        señal  = "ESPERAR"
        fuerza = "baja"

    razon = " | ".join(razones) if razones else "Sin señal clara"

    resultado = {
        "simbolo":       simbolo,
        "coin_id":       coin_id,
        "señal":         señal,
        "fuerza":        fuerza,
        "razon":         razon,
        "valor_actual":  round(cambio_24h, 2),   # compatibilidad con digestor_contexto
        "promedio":      round(cambio_7d, 2),     # compatibilidad con digestor_contexto
        "cambio_1h":     round(cambio_1h, 2),
        "cambio_24h":    round(cambio_24h, 2),
        "cambio_7d":     round(cambio_7d, 2),
        "sentimiento":   round(sentiment, 1),
        "en_trending":   en_trending,
        "volumen_24h":   volumen_24h,
        "precio":        precio,
        "ath_pct":       round(ath_pct, 1),
        "puntos_compra": puntos_compra,
        "puntos_venta":  puntos_venta,
        "timestamp":     datetime.now().strftime("%H:%M:%S"),
        "error":         False,
    }

    # Guarda en cache
    _cache_trends[simbolo] = resultado
    _cache_ts[simbolo]     = ahora

    return resultado

def ejecutar_google_trends() -> list:
    """Mantiene el nombre para compatibilidad — usa CoinGecko internamente."""
    resultados = []
    for simbolo in COINGECKO_MAP.keys():
        time.sleep(1)  # Respeta rate limit de CoinGecko free tier
        r = analizar_tendencia_activo(simbolo)
        resultados.append(r)
    return resultados

def obtener_reporte_trends() -> str:
    resultados = ejecutar_google_trends()
    lineas = []
    for r in resultados:
        if r.get("señal") not in ["ESPERAR", None] and not r.get("error"):
            lineas.append(
                f"{r['simbolo']}: {r['señal']} ({r['fuerza']}) | "
                f"1h={r['cambio_1h']:+.1f}% 24h={r['cambio_24h']:+.1f}% 7d={r['cambio_7d']:+.1f}% | "
                f"sentiment={r['sentimiento']}% | {r['razon']}"
            )
    return "\n".join(lineas) if lineas else "Sin señales de tendencia"