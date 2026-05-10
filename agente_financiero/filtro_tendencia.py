# agente_financiero/filtro_tendencia.py
import requests
import numpy as np
import pandas as pd

def obtener_velas_binance(simbolo: str, intervalo: str, limite: int = 100) -> pd.DataFrame:
    try:
        url = "https://api.binance.com/api/v3/klines"
        r = requests.get(url, params={"symbol": simbolo, "interval": intervalo, "limit": limite}, timeout=10)
        df = pd.DataFrame(r.json(), columns=[
            "timestamp","open","high","low","close","volume",
            "close_time","quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"
        ])
        for col in ["open","high","low","close","volume"]:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        print(f"[filtro_tendencia] Error {simbolo} {intervalo}: {e}")
        return pd.DataFrame()

def analizar_tendencia_mayor(simbolo: str) -> dict:
    # Analiza 3 timeframes mayores
    resultados = {}

    for intervalo, nombre in [("1h", "1hora"), ("4h", "4horas"), ("1d", "diario")]:
        df = obtener_velas_binance(simbolo, intervalo, limite=100)
        if df.empty or len(df) < 50:
            resultados[nombre] = {"tendencia": "desconocida"}
            continue

        closes = df["close"].values
        highs  = df["high"].values
        lows   = df["low"].values

        # Medias moviles
        ma20  = np.mean(closes[-20:])
        ma50  = np.mean(closes[-50:])
        precio = closes[-1]

        # EMA rapida vs lenta
        def ema(data, p):
            k = 2 / (p + 1)
            r = [data[0]]
            for x in data[1:]:
                r.append(x * k + r[-1] * (1 - k))
            return np.array(r)

        ema9  = ema(closes, 9)[-1]
        ema21 = ema(closes, 21)[-1]

        # HH/HL — Higher Highs / Higher Lows
        highs_recientes = highs[-10:]
        lows_recientes  = lows[-10:]
        hh = highs_recientes[-1] > highs_recientes[-5]
        hl = lows_recientes[-1]  > lows_recientes[-5]
        lh = highs_recientes[-1] < highs_recientes[-5]
        ll = lows_recientes[-1]  < lows_recientes[-5]

        # Determina tendencia
        puntos_alcista = sum([
            precio > ma20,
            precio > ma50,
            ma20 > ma50,
            ema9 > ema21,
            hh,
            hl,
        ])
        puntos_bajista = sum([
            precio < ma20,
            precio < ma50,
            ma20 < ma50,
            ema9 < ema21,
            lh,
            ll,
        ])

        if puntos_alcista >= 4:
            tendencia = "ALCISTA_FUERTE"
        elif puntos_alcista >= 3:
            tendencia = "ALCISTA"
        elif puntos_bajista >= 4:
            tendencia = "BAJISTA_FUERTE"
        elif puntos_bajista >= 3:
            tendencia = "BAJISTA"
        else:
            tendencia = "LATERAL"

        resultados[nombre] = {
            "tendencia":        tendencia,
            "precio":           round(precio, 4),
            "ma20":             round(ma20, 4),
            "ma50":             round(ma50, 4),
            "ema9":             round(ema9, 4),
            "ema21":            round(ema21, 4),
            "puntos_alcista":   puntos_alcista,
            "puntos_bajista":   puntos_bajista,
            "hh_hl":            hh and hl,
            "lh_ll":            lh and ll,
        }

    # Voto de mayoria entre timeframes
    tendencias = [r.get("tendencia", "LATERAL") for r in resultados.values()]
    votos_alcista = sum("ALCISTA" in t for t in tendencias)
    votos_bajista = sum("BAJISTA" in t for t in tendencias)

    if votos_alcista >= 2:
        tendencia_mayor = "ALCISTA"
        alineada_compra = True
        alineada_venta  = False
    elif votos_bajista >= 2:
        tendencia_mayor = "BAJISTA"
        alineada_compra = False
        alineada_venta  = True
    else:
        tendencia_mayor = "LATERAL"
        alineada_compra = False
        alineada_venta  = False

    return {
        "simbolo":         simbolo,
        "tendencia_mayor": tendencia_mayor,
        "alineada_compra": alineada_compra,
        "alineada_venta":  alineada_venta,
        "timeframes":      resultados,
        "votos_alcista":   votos_alcista,
        "votos_bajista":   votos_bajista,
    }

def filtrar_señal_por_tendencia(señal: dict) -> dict:
    simbolo = señal.get("simbolo", "")
    accion  = señal.get("señal_final", "ESPERAR")

    tendencia = analizar_tendencia_mayor(simbolo)

    # Filtra señales contra tendencia mayor
    if accion == "COMPRAR" and not tendencia["alineada_compra"]:
        return {
            "aprobada":        False,
            "razon":           f"Señal COMPRAR rechazada — tendencia mayor es {tendencia['tendencia_mayor']}",
            "tendencia":       tendencia,
        }
    if accion == "VENDER" and not tendencia["alineada_venta"]:
        return {
            "aprobada":        False,
            "razon":           f"Señal VENDER rechazada — tendencia mayor es {tendencia['tendencia_mayor']}",
            "tendencia":       tendencia,
        }

    return {
        "aprobada":        True,
        "razon":           f"Señal alineada con tendencia mayor {tendencia['tendencia_mayor']}",
        "tendencia":       tendencia,
    }

def analizar_tendencias_multiples(activos: list) -> dict:
    resultados = {}
    for simbolo in activos:
        print(f"[filtro_tendencia] Analizando {simbolo}...")
        resultados[simbolo] = analizar_tendencia_mayor(simbolo)
    return resultados