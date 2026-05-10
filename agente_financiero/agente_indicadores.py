# agente_financiero/agente_indicadores.py
import requests
import numpy as np
import pandas as pd
from datetime import datetime

ACTIVOS_CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

def obtener_velas_binance(simbolo: str, intervalo: str = "5m", limite: int = 200) -> pd.DataFrame:
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": simbolo, "interval": intervalo, "limit": limite}
        r = requests.get(url, params=params, timeout=10)
        df = pd.DataFrame(r.json(), columns=[
            "timestamp","open","high","low","close","volume",
            "close_time","quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"
        ])
        for col in ["open","high","low","close","volume"]:
            df[col] = df[col].astype(float)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        print(f"[agente_indicadores] Error {simbolo}: {e}")
        return pd.DataFrame()

def calcular_macd(closes: np.ndarray) -> dict:
    def ema(data, periodo):
        k = 2 / (periodo + 1)
        result = [data[0]]
        for precio in data[1:]:
            result.append(precio * k + result[-1] * (1 - k))
        return np.array(result)

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    macd_line = ema12 - ema26
    signal_line = ema(macd_line, 9)
    histograma = macd_line - signal_line

    # Detectar divergencia
    divergencia = None
    if len(histograma) >= 3:
        if histograma[-1] > histograma[-2] > histograma[-3]:
            divergencia = "alcista_acelerando"
        elif histograma[-1] < histograma[-2] < histograma[-3]:
            divergencia = "bajista_acelerando"
        elif histograma[-2] < 0 and histograma[-1] > histograma[-2]:
            divergencia = "posible_rebote_alcista"
        elif histograma[-2] > 0 and histograma[-1] < histograma[-2]:
            divergencia = "posible_caida_bajista"

    cruce = None
    if macd_line[-2] < signal_line[-2] and macd_line[-1] > signal_line[-1]:
        cruce = "CRUCE_ALCISTA"
    elif macd_line[-2] > signal_line[-2] and macd_line[-1] < signal_line[-1]:
        cruce = "CRUCE_BAJISTA"

    return {
        "macd": round(float(macd_line[-1]), 4),
        "signal": round(float(signal_line[-1]), 4),
        "histograma": round(float(histograma[-1]), 4),
        "divergencia": divergencia,
        "cruce": cruce,
    }

def calcular_estocastico(highs, lows, closes, k_periodo=14, d_periodo=3) -> dict:
    resultados_k = []
    for i in range(k_periodo - 1, len(closes)):
        h_max = np.max(highs[i - k_periodo + 1:i + 1])
        l_min = np.min(lows[i - k_periodo + 1:i + 1])
        if h_max - l_min == 0:
            resultados_k.append(50.0)
        else:
            k = ((closes[i] - l_min) / (h_max - l_min)) * 100
            resultados_k.append(k)

    k_vals = np.array(resultados_k)
    d_vals = np.convolve(k_vals, np.ones(d_periodo)/d_periodo, mode='valid')

    señal = "neutral"
    if k_vals[-1] < 20 and d_vals[-1] < 20:
        señal = "sobrevendido_COMPRA"
    elif k_vals[-1] > 80 and d_vals[-1] > 80:
        señal = "sobrecomprado_VENTA"
    elif k_vals[-2] < d_vals[-2] and k_vals[-1] > d_vals[-1] and k_vals[-1] < 50:
        señal = "cruce_alcista_zona_baja"
    elif k_vals[-2] > d_vals[-2] and k_vals[-1] < d_vals[-1] and k_vals[-1] > 50:
        señal = "cruce_bajista_zona_alta"

    return {
        "k": round(float(k_vals[-1]), 1),
        "d": round(float(d_vals[-1]), 1),
        "señal": señal,
    }

def calcular_vwap(df: pd.DataFrame) -> dict:
    df = df.copy()
    df["precio_tipico"] = (df["high"] + df["low"] + df["close"]) / 3
    df["vol_precio"] = df["precio_tipico"] * df["volume"]
    vwap = df["vol_precio"].cumsum() / df["volume"].cumsum()
    precio_actual = df["close"].iloc[-1]
    vwap_actual = vwap.iloc[-1]

    posicion = "sobre_vwap_ALCISTA" if precio_actual > vwap_actual else "bajo_vwap_BAJISTA"
    distancia = round(((precio_actual - vwap_actual) / vwap_actual) * 100, 3)

    return {
        "vwap": round(float(vwap_actual), 4),
        "precio": round(float(precio_actual), 4),
        "posicion": posicion,
        "distancia_pct": distancia,
    }

def calcular_obv(closes, volumes) -> dict:
    obv = [0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i-1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])

    obv = np.array(obv)
    tendencia_obv = "acumulacion" if obv[-1] > obv[-10] else "distribucion"
    aceleracion = "acelerando" if abs(obv[-1] - obv[-5]) > abs(obv[-5] - obv[-10]) else "desacelerando"

    return {
        "obv_actual": round(float(obv[-1]), 0),
        "tendencia": tendencia_obv,
        "aceleracion": aceleracion,
    }

def calcular_atr(highs, lows, closes, periodo=14) -> dict:
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        trs.append(tr)

    atr = np.mean(trs[-periodo:])
    precio = closes[-1]
    stop_loss_largo  = round(precio - (atr * 1.5), 4)
    stop_loss_corto  = round(precio + (atr * 1.5), 4)
    take_profit_1r   = round(precio + (atr * 2.0), 4)
    take_profit_2r   = round(precio + (atr * 3.0), 4)

    return {
        "atr": round(float(atr), 4),
        "atr_pct": round((atr / precio) * 100, 3),
        "stop_loss_largo": stop_loss_largo,
        "stop_loss_corto": stop_loss_corto,
        "take_profit_1r": take_profit_1r,
        "take_profit_2r": take_profit_2r,
    }

def calcular_williams_r(highs, lows, closes, periodo=14) -> dict:
    h_max = np.max(highs[-periodo:])
    l_min = np.min(lows[-periodo:])
    wr = ((h_max - closes[-1]) / (h_max - l_min)) * -100 if h_max != l_min else -50

    señal = "neutral"
    if wr < -80:
        señal = "sobrevendido_COMPRA"
    elif wr > -20:
        señal = "sobrecomprado_VENTA"

    return {"williams_r": round(float(wr), 1), "señal": señal}

def analizar_indicadores_completo() -> list:
    resultados = []

    for simbolo in ACTIVOS_CRYPTO:
        print(f"[agente_indicadores] Procesando {simbolo}...")
        df = obtener_velas_binance(simbolo, intervalo="5m", limite=200)
        if df.empty or len(df) < 50:
            continue

        closes  = df["close"].values
        highs   = df["high"].values
        lows    = df["low"].values
        volumes = df["volume"].values

        macd       = calcular_macd(closes)
        estoc      = calcular_estocastico(highs, lows, closes)
        vwap       = calcular_vwap(df)
        obv        = calcular_obv(closes, volumes)
        atr        = calcular_atr(highs, lows, closes)
        williams   = calcular_williams_r(highs, lows, closes)

        # Puntuacion de confluencia
        puntos_alcistas = 0
        puntos_bajistas = 0

        if macd.get("cruce") == "CRUCE_ALCISTA": puntos_alcistas += 2
        if macd.get("cruce") == "CRUCE_BAJISTA": puntos_bajistas += 2
        if macd.get("divergencia") in ["alcista_acelerando","posible_rebote_alcista"]: puntos_alcistas += 1
        if macd.get("divergencia") in ["bajista_acelerando","posible_caida_bajista"]: puntos_bajistas += 1
        if "COMPRA" in estoc.get("señal",""): puntos_alcistas += 2
        if "VENTA" in estoc.get("señal",""): puntos_bajistas += 2
        if "ALCISTA" in vwap.get("posicion",""): puntos_alcistas += 1
        if "BAJISTA" in vwap.get("posicion",""): puntos_bajistas += 1
        if obv.get("tendencia") == "acumulacion": puntos_alcistas += 1
        if obv.get("tendencia") == "distribucion": puntos_bajistas += 1
        if "COMPRA" in williams.get("señal",""): puntos_alcistas += 2
        if "VENTA" in williams.get("señal",""): puntos_bajistas += 2

        total = puntos_alcistas + puntos_bajistas
        confianza = round((max(puntos_alcistas, puntos_bajistas) / total) * 100) if total > 0 else 50
        señal_final = "COMPRAR" if puntos_alcistas > puntos_bajistas else "VENDER" if puntos_bajistas > puntos_alcistas else "ESPERAR"

        resultados.append({
            "simbolo": simbolo,
            "precio": vwap["precio"],
            "señal": señal_final,
            "confianza": confianza,
            "puntos_alcistas": puntos_alcistas,
            "puntos_bajistas": puntos_bajistas,
            "macd": macd,
            "estocastico": estoc,
            "vwap": vwap,
            "obv": obv,
            "atr": atr,
            "williams_r": williams,
        })

    return resultados

def obtener_reporte_indicadores() -> str:
    resultados = analizar_indicadores_completo()
    lineas = []
    for r in resultados:
        lineas.append(
            f"{r['simbolo']}: {r['señal']} | confianza={r['confianza']}% | "
            f"alcistas={r['puntos_alcistas']} bajistas={r['puntos_bajistas']} | "
            f"MACD={r['macd'].get('cruce','sin_cruce')} | "
            f"Estoc={r['estocastico']['señal']} | "
            f"VWAP={r['vwap']['posicion']} | "
            f"OBV={r['obv']['tendencia']} | "
            f"WR={r['williams_r']['señal']}"
        )
    return "\n".join(lineas)