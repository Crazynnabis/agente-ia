# agente_financiero/agente_volume_profile.py
import requests
import numpy as np
import pandas as pd
from datetime import datetime

ACTIVOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

def obtener_velas(simbolo: str, intervalo: str = "1h", limite: int = 200) -> pd.DataFrame:
    try:
        from agente_financiero.cache_mercado import obtener_velas as cache_velas
        return cache_velas(simbolo, intervalo, limite)
    except Exception as e:
        print(f"[agente_vp] Error cache {simbolo}: {e}")
        return pd.DataFrame()
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

def calcular_volume_profile(df: pd.DataFrame, bins: int = 30) -> dict:
    if df.empty or len(df) < 10:
        return {}

    precio_min = df["low"].min()
    precio_max = df["high"].max()
    precio_actual = float(df["close"].iloc[-1])

    # Crea bins de precio
    rangos = np.linspace(precio_min, precio_max, bins + 1)
    volumen_por_nivel = np.zeros(bins)

    for _, row in df.iterrows():
        # Distribuye el volumen entre high y low de cada vela
        for i in range(bins):
            nivel_bajo = rangos[i]
            nivel_alto = rangos[i + 1]
            # Si la vela toca este nivel
            if row["low"] <= nivel_alto and row["high"] >= nivel_bajo:
                overlap = min(row["high"], nivel_alto) - max(row["low"], nivel_bajo)
                rango_vela = row["high"] - row["low"] if row["high"] != row["low"] else 0.0001
                proporcion = overlap / rango_vela
                volumen_por_nivel[i] += row["volume"] * proporcion

    # POC — Point of Control (nivel con mas volumen)
    poc_idx   = np.argmax(volumen_por_nivel)
    poc_precio = (rangos[poc_idx] + rangos[poc_idx + 1]) / 2

    # VAH y VAL — Value Area High/Low (70% del volumen)
    vol_total     = np.sum(volumen_por_nivel)
    vol_objetivo  = vol_total * 0.70
    vol_acumulado = 0
    indices_va    = []

    indices_ordenados = np.argsort(volumen_por_nivel)[::-1]
    for idx in indices_ordenados:
        vol_acumulado += volumen_por_nivel[idx]
        indices_va.append(idx)
        if vol_acumulado >= vol_objetivo:
            break

    va_indices_sorted = sorted(indices_va)
    vah = (rangos[va_indices_sorted[-1]] + rangos[va_indices_sorted[-1] + 1]) / 2
    val = (rangos[va_indices_sorted[0]]  + rangos[va_indices_sorted[0]  + 1]) / 2

    # Posicion del precio actual respecto al perfil
    if precio_actual > vah:
        posicion = "SOBRE_VA — precio en zona premium, posible regreso al POC"
        señal    = "VENDER"
    elif precio_actual < val:
        posicion = "BAJO_VA — precio en zona descuento, posible rebote al POC"
        señal    = "COMPRAR"
    elif abs(precio_actual - poc_precio) / poc_precio < 0.003:
        posicion = "EN_POC — zona de mayor equilibrio, esperar ruptura"
        señal    = "ESPERAR"
    else:
        posicion = "DENTRO_VA — precio en zona de valor normal"
        señal    = "ESPERAR"

    # Nodos de alto volumen (HVN) y bajo volumen (LVN)
    umbral_hvn = np.percentile(volumen_por_nivel, 75)
    umbral_lvn = np.percentile(volumen_por_nivel, 25)

    hvn = [(rangos[i] + rangos[i+1])/2 for i in range(bins) if volumen_por_nivel[i] >= umbral_hvn]
    lvn = [(rangos[i] + rangos[i+1])/2 for i in range(bins) if volumen_por_nivel[i] <= umbral_lvn]

    # HVN mas cercano al precio actual
    hvn_cercano = min(hvn, key=lambda x: abs(x - precio_actual)) if hvn else None
    lvn_cercano = min(lvn, key=lambda x: abs(x - precio_actual)) if lvn else None

    dist_poc = round(((poc_precio - precio_actual) / precio_actual) * 100, 3)
    dist_vah = round(((vah - precio_actual) / precio_actual) * 100, 3)
    dist_val = round(((precio_actual - val) / precio_actual) * 100, 3)

    return {
        "precio_actual": round(precio_actual, 4),
        "poc":           round(poc_precio, 4),
        "vah":           round(vah, 4),
        "val":           round(val, 4),
        "dist_poc_pct":  dist_poc,
        "dist_vah_pct":  dist_vah,
        "dist_val_pct":  dist_val,
        "posicion":      posicion,
        "señal":         señal,
        "hvn_cercano":   round(hvn_cercano, 4) if hvn_cercano else None,
        "lvn_cercano":   round(lvn_cercano, 4) if lvn_cercano else None,
        "precio_min":    round(precio_min, 4),
        "precio_max":    round(precio_max, 4),
    }

def analizar_volume_profile_completo() -> list:
    resultados = []

    for simbolo in ACTIVOS:
        print(f"[agente_vp] Analizando {simbolo}...")

        # Analiza en dos timeframes
        vp_1h  = calcular_volume_profile(obtener_velas(simbolo, "1h",  200))
        vp_4h  = calcular_volume_profile(obtener_velas(simbolo, "4h",  100))

        if not vp_1h or not vp_4h:
            resultados.append({"simbolo": simbolo, "error": "Sin datos"})
            continue

        # Confluencia entre timeframes
        señales = [vp_1h.get("señal","ESPERAR"), vp_4h.get("señal","ESPERAR")]
        votos_compra = señales.count("COMPRAR")
        votos_venta  = señales.count("VENDER")

        if votos_compra == 2:
            señal_final = "COMPRAR"
            confluencia = "ALTA"
        elif votos_venta == 2:
            señal_final = "VENDER"
            confluencia = "ALTA"
        elif votos_compra == 1:
            señal_final = "COMPRAR"
            confluencia = "MEDIA"
        elif votos_venta == 1:
            señal_final = "VENDER"
            confluencia = "MEDIA"
        else:
            señal_final = "ESPERAR"
            confluencia = "BAJA"

        resultados.append({
            "simbolo":      simbolo,
            "vp_1h":        vp_1h,
            "vp_4h":        vp_4h,
            "señal_final":  señal_final,
            "confluencia":  confluencia,
            "votos_compra": votos_compra,
            "votos_venta":  votos_venta,
        })

    return resultados

def obtener_reporte_volume_profile() -> str:
    resultados = analizar_volume_profile_completo()
    lineas = []
    for r in resultados:
        if "error" not in r:
            vp = r["vp_1h"]
            lineas.append(
                f"{r['simbolo']}: {r['señal_final']} ({r['confluencia']}) | "
                f"POC={vp['poc']} ({vp['dist_poc_pct']}%) | "
                f"VAH={vp['vah']} VAL={vp['val']} | "
                f"posicion={vp['posicion'][:30]}"
            )
    return "\n".join(lineas)