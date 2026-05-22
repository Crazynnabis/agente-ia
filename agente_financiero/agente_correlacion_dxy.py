# agente_financiero/agente_correlacion_dxy.py
# Correlación BTC/DXY — el dólar y Bitcoin tienen correlación inversa fuerte
# Señal anticipatoria: DXY sube → BTC baja, DXY baja → BTC sube
# Usa yfinance — gratis, sin API key
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import yfinance as yf
import pandas as pd
import numpy as np
import time
from datetime import datetime

# Cache — 1 hora (DXY cambia lento)
_cache_dxy = {}
_cache_ts  = {}
TTL_DXY    = 3600

def obtener_datos_dxy() -> pd.DataFrame:
    """Descarga DXY (índice del dólar) de los últimos 30 días."""
    try:
        dxy = yf.download("DX-Y.NYB", period="30d", interval="1h", progress=False)
        if dxy.empty:
            dxy = yf.download("UUP", period="30d", interval="1h", progress=False)
        return dxy
    except Exception as e:
        print(f"[agente_dxy] Error descargando DXY: {e}")
        return pd.DataFrame()

def obtener_datos_btc() -> pd.DataFrame:
    """Descarga BTC de los últimos 30 días."""
    try:
        btc = yf.download("BTC-USD", period="30d", interval="1h", progress=False)
        return btc
    except Exception as e:
        print(f"[agente_dxy] Error descargando BTC: {e}")
        return pd.DataFrame()

def calcular_correlacion(dxy: pd.DataFrame, btc: pd.DataFrame) -> dict:
    """
    Calcula correlación entre DXY y BTC y genera señal anticipatoria.
    Si DXY sube fuerte → señal VENDER BTC
    Si DXY baja fuerte → señal COMPRAR BTC
    """
    try:
        # Alinea los datos por fecha
        dxy_close = dxy["Close"].squeeze()
        btc_close = btc["Close"].squeeze()

        df = pd.DataFrame({
            "dxy": dxy_close,
            "btc": btc_close,
        }).dropna()

        if len(df) < 10:
            return {"error": True, "razon": "Datos insuficientes"}

        # Correlación de Pearson últimas 24 velas (24h)
        ultimas_24 = df.tail(24)
        correlacion = ultimas_24["dxy"].corr(ultimas_24["btc"])

        # Cambios recientes
        dxy_cambio_1h  = float((df["dxy"].iloc[-1] - df["dxy"].iloc[-2]) / df["dxy"].iloc[-2] * 100) if len(df) >= 2 else 0
        dxy_cambio_24h = float((df["dxy"].iloc[-1] - df["dxy"].iloc[-24]) / df["dxy"].iloc[-24] * 100) if len(df) >= 24 else 0
        btc_cambio_1h  = float((df["btc"].iloc[-1] - df["btc"].iloc[-2]) / df["btc"].iloc[-2] * 100) if len(df) >= 2 else 0

        # Momentum DXY — tendencia de las últimas 6 velas
        ultimas_6  = df["dxy"].tail(6).values
        momentum   = float(np.polyfit(range(len(ultimas_6)), ultimas_6, 1)[0]) if len(ultimas_6) >= 2 else 0
        dxy_actual = float(df["dxy"].iloc[-1])
        btc_actual = float(df["btc"].iloc[-1])

        # ── Lógica de señal anticipatoria ────────────────────
        señal  = "ESPERAR"
        fuerza = "baja"
        razones = []

        # Correlación inversa confirmada (< -0.3 es significativa)
        corr_inversa = correlacion < -0.3

        if corr_inversa:
            # DXY subiendo fuerte → anticipamos caída BTC
            if dxy_cambio_1h > 0.3 and momentum > 0:
                señal  = "VENDER"
                fuerza = "alta" if dxy_cambio_1h > 0.5 else "media"
                razones.append(f"DXY +{dxy_cambio_1h:.2f}% en 1h con momentum alcista")
            elif dxy_cambio_24h > 1.0:
                señal  = "VENDER"
                fuerza = "media"
                razones.append(f"DXY +{dxy_cambio_24h:.2f}% en 24h")

            # DXY bajando fuerte → anticipamos subida BTC
            elif dxy_cambio_1h < -0.3 and momentum < 0:
                señal  = "COMPRAR"
                fuerza = "alta" if dxy_cambio_1h < -0.5 else "media"
                razones.append(f"DXY {dxy_cambio_1h:.2f}% en 1h con momentum bajista")
            elif dxy_cambio_24h < -1.0:
                señal  = "COMPRAR"
                fuerza = "media"
                razones.append(f"DXY {dxy_cambio_24h:.2f}% en 24h")

        # Divergencia — BTC no sigue al DXY (oportunidad)
        if señal == "ESPERAR" and abs(correlacion) > 0.5:
            if dxy_cambio_1h < -0.2 and btc_cambio_1h < -0.5:
                # DXY baja pero BTC también — divergencia, BTC debería rebotar
                señal  = "COMPRAR"
                fuerza = "media"
                razones.append(f"Divergencia: DXY baja {dxy_cambio_1h:.2f}% pero BTC no sigue")
            elif dxy_cambio_1h > 0.2 and btc_cambio_1h > 0.5:
                # DXY sube pero BTC también — divergencia, BTC debería corregir
                señal  = "VENDER"
                fuerza = "media"
                razones.append(f"Divergencia: DXY sube {dxy_cambio_1h:.2f}% pero BTC ignora")

        razon = " | ".join(razones) if razones else "Sin señal DXY/BTC"

        return {
            "señal":          señal,
            "fuerza":         fuerza,
            "razon":          razon,
            "correlacion":    round(float(correlacion), 3),
            "corr_inversa":   corr_inversa,
            "dxy_actual":     round(dxy_actual, 3),
            "dxy_cambio_1h":  round(dxy_cambio_1h, 3),
            "dxy_cambio_24h": round(dxy_cambio_24h, 3),
            "btc_actual":     round(btc_actual, 2),
            "btc_cambio_1h":  round(btc_cambio_1h, 3),
            "momentum_dxy":   round(momentum, 6),
            "error":          False,
        }

    except Exception as e:
        print(f"[agente_dxy] Error calculando correlación: {e}")
        return {"error": True, "razon": str(e)}

def analizar_correlacion_dxy() -> dict:
    """
    Función principal — analiza correlación BTC/DXY.
    Usa cache de 1 hora para no sobrecargar yfinance.
    """
    ahora     = time.time()
    cache_key = "dxy_btc"

    if cache_key in _cache_dxy and (ahora - _cache_ts.get(cache_key, 0)) < TTL_DXY:
        print(f"[agente_dxy] Cache hit")
        return _cache_dxy[cache_key]

    print(f"[agente_dxy] Analizando correlación BTC/DXY...")

    dxy = obtener_datos_dxy()
    btc = obtener_datos_btc()

    if dxy.empty or btc.empty:
        resultado = {
            "señal":       "ESPERAR",
            "fuerza":      "baja",
            "razon":       "Sin datos DXY o BTC",
            "correlacion": 0,
            "error":       True,
        }
    else:
        resultado = calcular_correlacion(dxy, btc)

    resultado["timestamp"] = datetime.now().strftime("%H:%M:%S")
    resultado["simbolo"]   = "BTCUSDT"

    print(f"[agente_dxy] Correlación={resultado.get('correlacion', 0)} | DXY={resultado.get('dxy_actual', 0)} | Señal={resultado.get('señal', 'N/A')}")

    _cache_dxy[cache_key] = resultado
    _cache_ts[cache_key]  = ahora

    return resultado
