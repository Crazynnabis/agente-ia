# agente_financiero/agente_google_trends.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pandas as pd
import numpy as np
import time
from datetime import datetime
from pytrends.request import TrendReq

# Cache global — Google Trends no cambia cada 15 min
_cache_trends = {}
_cache_ts     = {}
TTL_TRENDS    = 3600  # 1 hora de cache

KEYWORDS_MAP = {
    "BTCUSDT": ["Bitcoin", "BTC price", "buy Bitcoin"],
    "ETHUSDT": ["Ethereum", "ETH price", "buy Ethereum"],
    "SOLUSDT": ["Solana", "SOL crypto", "buy Solana"],
    "AAPL":    ["Apple stock", "AAPL", "Apple earnings"],
    "NVDA":    ["Nvidia stock", "NVDA", "buy Nvidia"],
    "MSFT":    ["Microsoft stock", "MSFT"],
    "TSLA":    ["Tesla stock", "TSLA", "buy Tesla"],
    "QQQ":     ["NASDAQ", "QQQ ETF", "tech stocks"],
    "SPY":     ["S&P 500", "SPY ETF", "stock market"],
}

def obtener_tendencias_cached(simbolo: str, keywords: list, periodo: str = "today 3-m") -> pd.DataFrame:
    ahora = time.time()
    if simbolo in _cache_trends and (ahora - _cache_ts.get(simbolo, 0)) < TTL_TRENDS:
        print(f"[agente_trends] Cache hit {simbolo}")
        return _cache_trends[simbolo]

    try:
        time.sleep(2)
        pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
        pytrends.build_payload(keywords[:3], cat=0, timeframe=periodo, geo="", gprop="")
        df = pytrends.interest_over_time()
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        if not df.empty:
            _cache_trends[simbolo] = df
            _cache_ts[simbolo]     = ahora
        return df
    except Exception as e:
        print(f"[agente_trends] Error {simbolo}: {e}")
        return pd.DataFrame()

def analizar_tendencia_activo(simbolo: str) -> dict:
    keywords         = KEYWORDS_MAP.get(simbolo, [simbolo])
    keyword_principal = keywords[0]

    print(f"[agente_trends] Analizando {simbolo}...")
    df = obtener_tendencias_cached(simbolo, keywords, periodo="today 3-m")

    if df.empty or keyword_principal not in df.columns:
        return {
            "simbolo":  simbolo,
            "señal":    "ESPERAR",
            "fuerza":   "baja",
            "razon":    "Sin datos de trends",
            "error":    True,
        }

    serie         = df[keyword_principal]
    valor_actual  = float(serie.iloc[-1])
    valor_semana  = float(serie.iloc[-2]) if len(serie) > 1 else valor_actual
    valor_mes     = float(serie.iloc[-5]) if len(serie) > 4 else valor_actual
    promedio_3m   = float(serie.mean())
    maximo_3m     = float(serie.max())

    cambio_semana = round(((valor_actual - valor_semana) / valor_semana * 100), 2) if valor_semana > 0 else 0
    cambio_mes    = round(((valor_actual - valor_mes)    / valor_mes    * 100), 2) if valor_mes    > 0 else 0
    vs_promedio   = round(((valor_actual - promedio_3m)  / promedio_3m  * 100), 2) if promedio_3m  > 0 else 0

    ultimas_4 = serie.tail(4).values
    momentum  = round(float(np.polyfit(range(len(ultimas_4)), ultimas_4, 1)[0]), 3) if len(ultimas_4) >= 2 else 0

    señal  = "ESPERAR"
    fuerza = "baja"
    razon  = "Sin señal clara"

    if valor_actual > promedio_3m * 1.5 and momentum > 0:
        señal  = "COMPRAR"
        fuerza = "alta"
        razon  = f"Busquedas {vs_promedio}% sobre promedio con momentum positivo"
    elif valor_actual > promedio_3m * 1.2 and cambio_semana > 10:
        señal  = "COMPRAR"
        fuerza = "media"
        razon  = f"Busquedas en aumento +{cambio_semana}% esta semana"
    elif valor_actual < promedio_3m * 0.7 and momentum < 0:
        señal  = "VENDER"
        fuerza = "media"
        razon  = f"Busquedas {vs_promedio}% bajo promedio — interes cayendo"
    elif cambio_semana < -20:
        señal  = "VENDER"
        fuerza = "media"
        razon  = f"Caida brusca -{abs(cambio_semana)}% esta semana"

    cerca_maximo = valor_actual >= maximo_3m * 0.9
    if cerca_maximo and señal == "COMPRAR":
        señal  = "PRECAUCION"
        fuerza = "baja"
        razon += " — cerca del maximo historico, posible techo"

    return {
        "simbolo":       simbolo,
        "keyword":       keyword_principal,
        "valor_actual":  round(valor_actual, 1),
        "promedio_3m":   round(promedio_3m, 1),
        "maximo_3m":     round(maximo_3m, 1),
        "cambio_semana": cambio_semana,
        "cambio_mes":    cambio_mes,
        "vs_promedio":   vs_promedio,
        "momentum":      momentum,
        "cerca_maximo":  cerca_maximo,
        "señal":         señal,
        "fuerza":        fuerza,
        "razon":         razon,
        "timestamp":     datetime.now().strftime("%H:%M:%S"),
    }

def ejecutar_google_trends() -> list:
    resultados = []
    for simbolo in KEYWORDS_MAP.keys():
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
                f"valor={r['valor_actual']} vs prom={r['promedio_3m']} | "
                f"semana={r['cambio_semana']}% | {r['razon']}"
            )
    return "\n".join(lineas) if lineas else "Sin señales de Google Trends"