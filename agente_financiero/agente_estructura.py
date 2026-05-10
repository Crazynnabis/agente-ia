# agente_financiero/agente_estructura.py
import requests
import numpy as np
import pandas as pd
from datetime import datetime

ACTIVOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

def obtener_velas(simbolo: str, intervalo: str = "15m", limite: int = 100) -> pd.DataFrame:
    try:
        url = "https://api.binance.com/api/v3/klines"
        r = requests.get(url, params={"symbol": simbolo, "interval": intervalo, "limit": limite}, timeout=10)
        df = pd.DataFrame(r.json(), columns=[
            "timestamp","open","high","low","close","volume",
            "close_time","quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"
        ])
        for col in ["open","high","low","close","volume"]:
            df[col] = df[col].astype(float)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        return pd.DataFrame()

def detectar_swing_points(df: pd.DataFrame, fuerza: int = 3) -> dict:
    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values

    swing_highs = []
    swing_lows  = []

    for i in range(fuerza, len(df) - fuerza):
        # Swing high — maximo local
        if all(highs[i] >= highs[i-j] for j in range(1, fuerza+1)) and \
           all(highs[i] >= highs[i+j] for j in range(1, fuerza+1)):
            swing_highs.append({"idx": i, "precio": highs[i], "timestamp": df["timestamp"].iloc[i]})

        # Swing low — minimo local
        if all(lows[i] <= lows[i-j] for j in range(1, fuerza+1)) and \
           all(lows[i] <= lows[i+j] for j in range(1, fuerza+1)):
            swing_lows.append({"idx": i, "precio": lows[i], "timestamp": df["timestamp"].iloc[i]})

    return {"swing_highs": swing_highs[-5:], "swing_lows": swing_lows[-5:]}

def detectar_bos_choch(swings: dict, precio_actual: float) -> dict:
    highs = swings["swing_highs"]
    lows  = swings["swing_lows"]

    if len(highs) < 2 or len(lows) < 2:
        return {"estructura": "INDEFINIDA", "señal": "ESPERAR"}

    # Detecta HH/HL (Higher Highs / Higher Lows) — tendencia alcista
    hh = highs[-1]["precio"] > highs[-2]["precio"]
    hl = lows[-1]["precio"]  > lows[-2]["precio"]

    # Detecta LH/LL (Lower Highs / Lower Lows) — tendencia bajista
    lh = highs[-1]["precio"] < highs[-2]["precio"]
    ll = lows[-1]["precio"]  < lows[-2]["precio"]

    # BOS — Break of Structure
    ultimo_high = highs[-1]["precio"]
    ultimo_low  = lows[-1]["precio"]

    bos_alcista = precio_actual > ultimo_high
    bos_bajista = precio_actual < ultimo_low

    # CHoCH — Change of Character (cambio de tendencia)
    if hh and hl:
        estructura = "TENDENCIA_ALCISTA"
        if lh:
            choch = "CHOCH_BAJISTA — posible cambio de tendencia"
            señal = "VENDER"
        else:
            choch = None
            señal = "COMPRAR"
    elif lh and ll:
        estructura = "TENDENCIA_BAJISTA"
        if hl:
            choch = "CHOCH_ALCISTA — posible cambio de tendencia"
            señal = "COMPRAR"
        else:
            choch = None
            señal = "VENDER"
    else:
        estructura = "LATERAL"
        choch = None
        señal = "ESPERAR"

    # BOS confirma continuacion
    if bos_alcista and estructura == "TENDENCIA_ALCISTA":
        bos = "BOS_ALCISTA — continuacion confirmada"
        señal = "COMPRAR"
    elif bos_bajista and estructura == "TENDENCIA_BAJISTA":
        bos = "BOS_BAJISTA — continuacion confirmada"
        señal = "VENDER"
    else:
        bos = None

    # Zonas de liquidez
    zona_liquidez_arriba = max([h["precio"] for h in highs])
    zona_liquidez_abajo  = min([l["precio"] for l in lows])
    dist_liquidez_arriba = round(((zona_liquidez_arriba - precio_actual) / precio_actual) * 100, 3)
    dist_liquidez_abajo  = round(((precio_actual - zona_liquidez_abajo) / precio_actual) * 100, 3)

    return {
        "estructura":           estructura,
        "hh_hl":                hh and hl,
        "lh_ll":                lh and ll,
        "bos":                  bos,
        "choch":                choch,
        "señal":                señal,
        "zona_liquidez_arriba": round(zona_liquidez_arriba, 4),
        "zona_liquidez_abajo":  round(zona_liquidez_abajo, 4),
        "dist_liquidez_arriba": dist_liquidez_arriba,
        "dist_liquidez_abajo":  dist_liquidez_abajo,
        "ultimo_high":          round(ultimo_high, 4),
        "ultimo_low":           round(ultimo_low, 4),
    }

def analizar_estructura_completo() -> list:
    resultados = []

    for simbolo in ACTIVOS:
        print(f"[agente_estructura] Analizando {simbolo}...")

        # Analiza en 3 timeframes
        analisis_tf = {}
        for intervalo in ["5m", "15m", "1h"]:
            df = obtener_velas(simbolo, intervalo=intervalo, limite=100)
            if df.empty:
                continue
            precio_actual = float(df["close"].iloc[-1])
            swings = detectar_swing_points(df)
            bos    = detectar_bos_choch(swings, precio_actual)
            analisis_tf[intervalo] = {
                "precio":   precio_actual,
                "swings":   swings,
                "analisis": bos,
            }

        if not analisis_tf:
            resultados.append({"simbolo": simbolo, "error": "Sin datos"})
            continue

        # Voto de mayoria entre timeframes
        señales = [v["analisis"]["señal"] for v in analisis_tf.values()]
        votos_compra = señales.count("COMPRAR")
        votos_venta  = señales.count("VENDER")

        if votos_compra >= 2:
            señal_final   = "COMPRAR"
            confluencia   = "ALTA" if votos_compra == 3 else "MEDIA"
        elif votos_venta >= 2:
            señal_final   = "VENDER"
            confluencia   = "ALTA" if votos_venta == 3 else "MEDIA"
        else:
            señal_final   = "ESPERAR"
            confluencia   = "BAJA"

        # Toma el analisis del timeframe principal (15m)
        analisis_principal = analisis_tf.get("15m", list(analisis_tf.values())[0])

        resultados.append({
            "simbolo":     simbolo,
            "precio":      analisis_principal["precio"],
            "estructura":  analisis_principal["analisis"]["estructura"],
            "bos":         analisis_principal["analisis"]["bos"],
            "choch":       analisis_principal["analisis"]["choch"],
            "timeframes":  {tf: v["analisis"]["estructura"] for tf, v in analisis_tf.items()},
            "señales_tf":  {tf: v["analisis"]["señal"] for tf, v in analisis_tf.items()},
            "zona_liq_arriba": analisis_principal["analisis"]["zona_liquidez_arriba"],
            "zona_liq_abajo":  analisis_principal["analisis"]["zona_liquidez_abajo"],
            "dist_liq_arriba": analisis_principal["analisis"]["dist_liquidez_arriba"],
            "dist_liq_abajo":  analisis_principal["analisis"]["dist_liquidez_abajo"],
            "señal_final": señal_final,
            "confluencia": confluencia,
            "votos_compra": votos_compra,
            "votos_venta":  votos_venta,
        })

    return resultados

def obtener_reporte_estructura() -> str:
    resultados = analizar_estructura_completo()
    lineas = []
    for r in resultados:
        if "error" not in r:
            lineas.append(
                f"{r['simbolo']}: {r['señal_final']} ({r['confluencia']}) | "
                f"estructura={r['estructura']} | "
                f"bos={r.get('bos','ninguno')} | "
                f"choch={r.get('choch','ninguno')} | "
                f"zona_liq_arriba={r['zona_liq_arriba']} ({r['dist_liq_arriba']}%)"
            )
    return "\n".join(lineas)