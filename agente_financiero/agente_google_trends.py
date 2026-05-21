# agente_financiero/agente_google_trends.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pandas as pd
import numpy as np
import time
from datetime import datetime
from pytrends.request import TrendReq

# Cache global — 4 horas, Google Trends cambia muy lento
_cache_trends = {}
_cache_ts     = {}
TTL_TRENDS    = 14400  # 4 horas

# Solo 3 simbolos clave para ser rapido
KEYWORDS_MAP = {
    "BTCUSDT": ["Bitcoin", "buy Bitcoin"],
    "ETHUSDT": ["Ethereum", "buy Ethereum"],
    "SOLUSDT": ["Solana", "SOL crypto"],
}

def obtener_tendencias_cached(simbolo: str, keywords: list) -> pd.DataFrame:
    ahora = time.time()

    # Cache hit — no hace request
    if simbolo in _cache_trends and (ahora - _cache_ts.get(simbolo, 0)) < TTL_TRENDS:
        print(f"[agente_trends] Cache hit {simbolo}")
        return _cache_trends[simbolo]

    try:
        time.sleep(1)  # Reducido de 2s a 1s
        pytrends = TrendReq(hl="en-US", tz=360, timeout=(5, 15))
        pytrends.build_payload(keywords[:2], cat=0, timeframe="today 1-m", geo="", gprop="")
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
    keywords          = KEYWORDS_MAP.get(simbolo, [simbolo])
    keyword_principal = keywords[0]

    print(f"[agente_trends] Analizando {simbolo}...")
    df = obtener_tendencias_cached(simbolo, keywords)

    if df.empty or keyword_principal not in df.columns:
        return {
            "simbolo": simbolo,
            "señal":   "ESPERAR",
            "fuerza":  "baja",
            "razon":   "Sin datos de trends",
            "error":   True,
        }

    serie        = df[keyword_principal]
    valor_actual = float(serie.iloc[-1])
    valor_semana = float(serie.iloc[-2]) if len(serie) > 1 else valor_actual
    promedio     = float(serie.mean())
    maximo       = float(serie.max())

    cambio_semana = round(((valor_actual - valor_semana) / valor_semana * 100), 2) if valor_semana > 0 else 0
    vs_promedio   = round(((valor_actual - promedio) / promedio * 100), 2) if promedio > 0 else 0

    ultimas_4 = serie.tail(4).values
    momentum  = round(float(np.polyfit(range(len(ultimas_4)), ultimas_4, 1)[0]), 3) if len(ultimas_4) >= 2 else 0

    señal  = "ESPERAR"
    fuerza = "baja"
    razon  = "Sin señal clara"

    if valor_actual > promedio * 1.5 and momentum > 0:
        señal  = "COMPRAR"
        fuerza = "alta"
        razon  = f"Busquedas {vs_promedio}% sobre promedio con momentum positivo"
    elif valor_actual > promedio * 1.2 and cambio_semana > 10:
        señal  = "COMPRAR"
        fuerza = "media"
        razon  = f"Busquedas en aumento +{cambio_semana}% esta semana"
    elif valor_actual < promedio * 0.7 and momentum < 0:
        señal  = "VENDER"
        fuerza = "media"
        razon  = f"Busquedas {vs_promedio}% bajo promedio"
    elif cambio_semana < -20:
        señal  = "VENDER"
        fuerza = "media"
        razon  = f"Caida brusca -{abs(cambio_semana)}% esta semana"

    if valor_actual >= maximo * 0.9 and señal == "COMPRAR":
        señal  = "PRECAUCION"
        fuerza = "baja"
        razon += " — cerca del maximo historico"

    return {
        "simbolo":       simbolo,
        "keyword":       keyword_principal,
        "valor_actual":  round(valor_actual, 1),
        "promedio":      round(promedio, 1),
        "maximo":        round(maximo, 1),
        "cambio_semana": cambio_semana,
        "vs_promedio":   vs_promedio,
        "momentum":      momentum,
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
                f"valor={r['valor_actual']} vs prom={r['promedio']} | "
                f"semana={r['cambio_semana']}% | {r['razon']}"
            )
    return "\n".join(lineas) if lineas else "Sin señales de Google Trends"