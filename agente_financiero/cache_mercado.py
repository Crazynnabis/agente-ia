# agente_financiero/cache_mercado.py
import requests
import pandas as pd
import time
from threading import Lock

_cache = {}
_lock  = Lock()

TTL_VELAS  = 60   # segundos — velas expiran en 1 minuto
TTL_PRECIO = 10   # segundos — precio expira en 10 segundos
TTL_FUTUROS = 30  # segundos — futuros expiran en 30 segundos

def obtener_velas(simbolo: str, intervalo: str = "5m", limite: int = 200) -> pd.DataFrame:
    clave = f"velas_{simbolo}_{intervalo}_{limite}"
    ahora = time.time()

    with _lock:
        if clave in _cache:
            datos, ts = _cache[clave]
            if ahora - ts < TTL_VELAS:
                return datos.copy()

    try:
        url = "https://api.binance.com/api/v3/klines"
        r   = requests.get(url, params={"symbol": simbolo, "interval": intervalo, "limit": limite}, timeout=10)
        df  = pd.DataFrame(r.json(), columns=[
            "timestamp","open","high","low","close","volume",
            "close_time","quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"
        ])
        for col in ["open","high","low","close","volume"]:
            df[col] = df[col].astype(float)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        with _lock:
            _cache[clave] = (df, time.time())
        return df.copy()
    except Exception as e:
        print(f"[cache] Error {simbolo} {intervalo}: {e}")
        return pd.DataFrame()

def obtener_precio_actual(simbolo: str) -> float:
    clave = f"precio_{simbolo}"
    ahora = time.time()

    with _lock:
        if clave in _cache:
            precio, ts = _cache[clave]
            if ahora - ts < TTL_PRECIO:
                return precio

    try:
        r      = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": simbolo}, timeout=5
        )
        precio = float(r.json()["price"])
        with _lock:
            _cache[clave] = (precio, time.time())
        return precio
    except:
        return 0.0

def obtener_futuros_velas(simbolo: str, intervalo: str = "5m", limite: int = 200) -> pd.DataFrame:
    clave = f"fut_{simbolo}_{intervalo}_{limite}"
    ahora = time.time()

    with _lock:
        if clave in _cache:
            datos, ts = _cache[clave]
            if ahora - ts < TTL_FUTUROS:
                return datos.copy()

    try:
        url = "https://fapi.binance.com/fapi/v1/klines"
        r   = requests.get(url, params={"symbol": simbolo, "interval": intervalo, "limit": limite}, timeout=10)
        df  = pd.DataFrame(r.json(), columns=[
            "timestamp","open","high","low","close","volume",
            "close_time","quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"
        ])
        for col in ["open","high","low","close","volume"]:
            df[col] = df[col].astype(float)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        with _lock:
            _cache[clave] = (df, time.time())
        return df.copy()
    except Exception as e:
        print(f"[cache] Error futuros {simbolo}: {e}")
        return pd.DataFrame()

def limpiar_cache():
    ahora     = time.time()
    with _lock:
        expiradas = [k for k, (_, ts) in _cache.items() if ahora - ts > TTL_VELAS * 2]
        for k in expiradas:
            del _cache[k]
    print(f"[cache] Limpiadas {len(expiradas)} entradas expiradas")

def estado_cache() -> dict:
    with _lock:
        return {
            "entradas": len(_cache),
            "claves":   list(_cache.keys()),
        }