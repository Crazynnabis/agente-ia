# agente_financiero/agente_vwap_reversion.py
import numpy as np
import pandas as pd
from datetime import datetime
from agente_financiero.cache_mercado import obtener_velas

ACTIVOS_CRYPTO   = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
ACTIVOS_ACCIONES = ["AAPL", "NVDA", "MSFT", "TSLA", "SPY", "QQQ"]

def calcular_vwap_completo(df: pd.DataFrame) -> pd.Series:
    df = df.copy()
    df["precio_tipico"] = (df["high"] + df["low"] + df["close"]) / 3
    df["vol_precio"]    = df["precio_tipico"] * df["volume"]
    vwap = df["vol_precio"].cumsum() / df["volume"].cumsum()
    return vwap

def calcular_bandas_vwap(df: pd.DataFrame, vwap: pd.Series, desviaciones: int = 2) -> dict:
    df = df.copy()
    df["precio_tipico"] = (df["high"] + df["low"] + df["close"]) / 3
    varianza = ((df["precio_tipico"] - vwap) ** 2 * df["volume"]).cumsum() / df["volume"].cumsum()
    std_dev  = np.sqrt(varianza)
    return {
        "vwap":    vwap,
        "banda_sup_1": vwap + std_dev,
        "banda_inf_1": vwap - std_dev,
        "banda_sup_2": vwap + (std_dev * desviaciones),
        "banda_inf_2": vwap - (std_dev * desviaciones),
    }

def analizar_vwap_reversion(simbolo: str, intervalo: str = "5m") -> dict:
    try:
        df = obtener_velas(simbolo, intervalo, 200)
        if df.empty or len(df) < 20:
            return {"simbolo": simbolo, "error": "Sin datos"}

        vwap   = calcular_vwap_completo(df)
        bandas = calcular_bandas_vwap(df, vwap)

        precio_actual = float(df["close"].iloc[-1])
        vwap_actual   = float(vwap.iloc[-1])
        banda_sup_2   = float(bandas["banda_sup_2"].iloc[-1])
        banda_inf_2   = float(bandas["banda_inf_2"].iloc[-1])
        banda_sup_1   = float(bandas["banda_sup_1"].iloc[-1])
        banda_inf_1   = float(bandas["banda_inf_1"].iloc[-1])

        distancia_vwap_pct = round(((precio_actual - vwap_actual) / vwap_actual) * 100, 3)

        # Detecta posicion respecto al VWAP
        if precio_actual > banda_sup_2:
            zona    = "EXTREMO_SUPERIOR"
            señal   = "VENDER"
            fuerza  = "muy_alta"
            razon   = f"Precio {distancia_vwap_pct}% sobre VWAP — reversión alta probabilidad"
        elif precio_actual > banda_sup_1:
            zona    = "ZONA_PREMIUM"
            señal   = "VENDER"
            fuerza  = "alta"
            razon   = f"Precio en zona premium {distancia_vwap_pct}% sobre VWAP"
        elif precio_actual < banda_inf_2:
            zona    = "EXTREMO_INFERIOR"
            señal   = "COMPRAR"
            fuerza  = "muy_alta"
            razon   = f"Precio {distancia_vwap_pct}% bajo VWAP — rebote alta probabilidad"
        elif precio_actual < banda_inf_1:
            zona    = "ZONA_DESCUENTO"
            señal   = "COMPRAR"
            fuerza  = "alta"
            razon   = f"Precio en zona descuento {distancia_vwap_pct}% bajo VWAP"
        else:
            zona    = "ZONA_EQUILIBRIO"
            señal   = "ESPERAR"
            fuerza  = "baja"
            razon   = "Precio dentro del rango VWAP normal"

        # Stop loss y take profit basados en VWAP
        if señal == "COMPRAR":
            sl  = round(banda_inf_2 * 0.998, 4)
            tp1 = round(vwap_actual, 4)
            tp2 = round(banda_sup_1, 4)
        elif señal == "VENDER":
            sl  = round(banda_sup_2 * 1.002, 4)
            tp1 = round(vwap_actual, 4)
            tp2 = round(banda_inf_1, 4)
        else:
            sl  = 0
            tp1 = 0
            tp2 = 0

        # Historial reciente — cuantas veces revirtio al VWAP
        precios_recientes = df["close"].values[-20:]
        reversiones = 0
        for i in range(1, len(precios_recientes)):
            dist_actual   = abs(float(vwap.values[-20+i]) - precios_recientes[i])
            dist_anterior = abs(float(vwap.values[-20+i]) - precios_recientes[i-1])
            if dist_actual < dist_anterior:
                reversiones += 1
        tasa_reversion = round(reversiones / 19 * 100, 1)
        
        return {
            "simbolo":           simbolo,
            "precio":            round(precio_actual, 4),
            "vwap":              round(vwap_actual, 4),
            "distancia_pct":     distancia_vwap_pct,
            "zona":              zona,
            "señal":             señal,
            "fuerza":            fuerza,
            "razon":             razon,
            "stop_loss":         sl,
            "take_profit_1":     tp1,
            "take_profit_2":     tp2,
            "banda_sup_2":       round(banda_sup_2, 4),
            "banda_inf_2":       round(banda_inf_2, 4),
            "tasa_reversion_pct":tasa_reversion,
            "timestamp":         datetime.now().strftime("%H:%M:%S"),
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def ejecutar_vwap_reversion() -> list:
    resultados = []
    print("[agente_vwap] Analizando crypto...")
    for simbolo in ACTIVOS_CRYPTO:
        r = analizar_vwap_reversion(simbolo, "5m")
        if "error" not in r:
            resultados.append(r)

    print("[agente_vwap] Analizando acciones...")
    for simbolo in ACTIVOS_ACCIONES:
        r = analizar_vwap_reversion(simbolo, "5m")
        if "error" not in r:
            resultados.append(r)

    return resultados

def obtener_reporte_vwap() -> str:
    resultados = ejecutar_vwap_reversion()
    lineas = []
    for r in resultados:
        if r.get("señal") != "ESPERAR":
            lineas.append(
                f"{r['simbolo']}: {r['señal']} ({r['fuerza']}) | "
                f"zona={r['zona']} | dist={r['distancia_pct']}% | "
                f"reversion={r['tasa_reversion_pct']}%"
            )
    return "\n".join(lineas) if lineas else "Sin señales VWAP Reversion"