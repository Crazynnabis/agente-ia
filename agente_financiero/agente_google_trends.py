# agente_financiero/agente_google_trends.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pytrends.request import TrendReq

# Keywords por activo
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

def obtener_tendencias(keywords: list, periodo: str = "today 3-m") -> pd.DataFrame:
    try:
        import time
        time.sleep(3)
        pytrends = TrendReq(hl="en-US", tz=360, timeout=(10, 25))
        pytrends.build_payload(keywords[:5], cat=0, timeframe=periodo, geo="", gprop="")
        df = pytrends.interest_over_time()
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        return df
    except Exception as e:
        print(f"[agente_trends] Error: {e}")
        return pd.DataFrame()

        pytrends.build_payload(keywords[:5], cat=0, timeframe=periodo, geo="", gprop="")
        df = pytrends.interest_over_time()
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        return df
    except Exception as e:
        print(f"[agente_trends] Error: {e}")
        return pd.DataFrame()

def analizar_tendencia_activo(simbolo: str) -> dict:
    keywords = KEYWORDS_MAP.get(simbolo, [simbolo])
    keyword_principal = keywords[0]

    print(f"[agente_trends] Analizando {simbolo} — {keyword_principal}...")

    df = obtener_tendencias(keywords[:3], periodo="today 3-m")
    if df.empty or keyword_principal not in df.columns:
        return {"simbolo": simbolo, "error": "Sin datos de trends"}

    serie = df[keyword_principal]

    # Valores actuales vs histórico
    valor_actual   = float(serie.iloc[-1])
    valor_semana   = float(serie.iloc[-2]) if len(serie) > 1 else valor_actual
    valor_mes      = float(serie.iloc[-5]) if len(serie) > 4 else valor_actual
    promedio_3m    = float(serie.mean())
    maximo_3m      = float(serie.max())
    minimo_3m      = float(serie.min())

    # Cambios
    cambio_semana  = round(((valor_actual - valor_semana) / valor_semana * 100), 2) if valor_semana > 0 else 0
    cambio_mes     = round(((valor_actual - valor_mes) / valor_mes * 100), 2) if valor_mes > 0 else 0
    vs_promedio    = round(((valor_actual - promedio_3m) / promedio_3m * 100), 2) if promedio_3m > 0 else 0

    # Momentum de búsquedas
    ultimas_4 = serie.tail(4).values
    momentum  = round(float(np.polyfit(range(len(ultimas_4)), ultimas_4, 1)[0]), 3)

    # Señal basada en tendencia de búsquedas
    # Retail busca ANTES de comprar — subida de búsquedas predice subida de precio
    señal  = "ESPERAR"
    fuerza = "baja"
    razon  = ""

    if valor_actual > promedio_3m * 1.5 and momentum > 0:
        señal  = "COMPRAR"
        fuerza = "alta"
        razon  = f"Búsquedas {vs_promedio}% sobre promedio con momentum positivo"
    elif valor_actual > promedio_3m * 1.2 and cambio_semana > 10:
        señal  = "COMPRAR"
        fuerza = "media"
        razon  = f"Búsquedas en aumento +{cambio_semana}% esta semana"
    elif valor_actual < promedio_3m * 0.7 and momentum < 0:
        señal  = "VENDER"
        fuerza = "media"
        razon  = f"Búsquedas {vs_promedio}% bajo promedio — interés cayendo"
    elif cambio_semana < -20:
        señal  = "VENDER"
        fuerza = "media"
        razon  = f"Caída brusca de búsquedas -{abs(cambio_semana)}%"

    # Detecta picos — cuando búsquedas llegan a máximo histórico suele ser techo
    cerca_maximo = valor_actual >= maximo_3m * 0.9
    if cerca_maximo and señal == "COMPRAR":
        señal  = "PRECAUCION"
        fuerza = "baja"
        razon  += " — PERO cerca del máximo histórico, posible techo"

    return {
        "simbolo":        simbolo,
        "keyword":        keyword_principal,
        "valor_actual":   round(valor_actual, 1),
        "promedio_3m":    round(promedio_3m, 1),
        "maximo_3m":      round(maximo_3m, 1),
        "cambio_semana":  cambio_semana,
        "cambio_mes":     cambio_mes,
        "vs_promedio":    vs_promedio,
        "momentum":       momentum,
        "cerca_maximo":   cerca_maximo,
        "señal":          señal,
        "fuerza":         fuerza,
        "razon":          razon,
        "timestamp":      datetime.now().strftime("%H:%M:%S"),
    }

def ejecutar_google_trends() -> list:
    resultados = []
    # Analiza de 3 en 3 para evitar rate limiting de Google
    simbolos = list(KEYWORDS_MAP.keys())
    for simbolo in simbolos:
        r = analizar_tendencia_activo(simbolo)
        if "error" not in r:
            resultados.append(r)
        import time
        time.sleep(2)  # Pausa para evitar bloqueo de Google
    return resultados

def obtener_reporte_trends() -> str:
    resultados = ejecutar_google_trends()
    lineas = []
    for r in resultados:
        if r.get("señal") != "ESPERAR":
            lineas.append(
                f"{r['simbolo']}: {r['señal']} ({r['fuerza']}) | "
                f"valor={r['valor_actual']} vs promedio={r['promedio_3m']} | "
                f"semana={r['cambio_semana']}% | {r['razon']}"
            )
    return "\n".join(lineas) if lineas else "Sin señales de Google Trends"