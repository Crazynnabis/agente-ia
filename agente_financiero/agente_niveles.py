# agente_financiero/agente_niveles.py
import requests
import numpy as np
import pandas as pd
from datetime import datetime

def obtener_velas_binance(simbolo: str, intervalo: str = "1d", limite: int = 365) -> pd.DataFrame:
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
        print(f"[agente_niveles] Error {simbolo}: {e}")
        return pd.DataFrame()

def detectar_zonas_sd(df: pd.DataFrame, sensibilidad: float = 0.015) -> dict:
    if df.empty or len(df) < 30:
        return {}

    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values
    vols   = df["volume"].values
    precio_actual = closes[-1]

    zonas_oferta     = []  # resistencias — donde el precio cayó con fuerza
    zonas_demanda    = []  # soportes — donde el precio rebotó con fuerza

    for i in range(2, len(df) - 2):
        # Zona de demanda: vela bajista fuerte seguida de subida
        if (closes[i] < df["open"].values[i] and
            closes[i+1] > df["open"].values[i+1] and
            closes[i+2] > closes[i+1] and
            vols[i] > np.mean(vols[max(0,i-10):i]) * 1.2):
            zonas_demanda.append({
                "precio_base": round(lows[i], 4),
                "precio_tope": round(closes[i], 4),
                "fuerza": round(vols[i] / np.mean(vols[max(0,i-10):i]), 2),
                "fecha": str(df["timestamp"].iloc[i].date()),
                "toques": 0,
            })

        # Zona de oferta: vela alcista fuerte seguida de caída
        if (closes[i] > df["open"].values[i] and
            closes[i+1] < df["open"].values[i+1] and
            closes[i+2] < closes[i+1] and
            vols[i] > np.mean(vols[max(0,i-10):i]) * 1.2):
            zonas_oferta.append({
                "precio_base": round(closes[i], 4),
                "precio_tope": round(highs[i], 4),
                "fuerza": round(vols[i] / np.mean(vols[max(0,i-10):i]), 2),
                "fecha": str(df["timestamp"].iloc[i].date()),
                "toques": 0,
            })

    # Cuenta toques — cuantas veces el precio volvio a esa zona
    for zona in zonas_demanda + zonas_oferta:
        for close in closes:
            if zona["precio_base"] * (1 - sensibilidad) <= close <= zona["precio_tope"] * (1 + sensibilidad):
                zona["toques"] += 1

    # Filtra zonas mas relevantes — mas toques y mas recientes
    zonas_demanda = sorted(zonas_demanda, key=lambda z: (z["toques"], z["fuerza"]), reverse=True)[:5]
    zonas_oferta  = sorted(zonas_oferta,  key=lambda z: (z["toques"], z["fuerza"]), reverse=True)[:5]

    # Zona mas cercana al precio actual
    soporte_cercano = min(
        [z for z in zonas_demanda if z["precio_tope"] < precio_actual],
        key=lambda z: precio_actual - z["precio_tope"],
        default=None
    )
    resistencia_cercana = min(
        [z for z in zonas_oferta if z["precio_base"] > precio_actual],
        key=lambda z: z["precio_base"] - precio_actual,
        default=None
    )

    # Distancias
    dist_soporte     = round(((precio_actual - soporte_cercano["precio_tope"]) / precio_actual) * 100, 2) if soporte_cercano else None
    dist_resistencia = round(((resistencia_cercana["precio_base"] - precio_actual) / precio_actual) * 100, 2) if resistencia_cercana else None

    # Posicion en rango
    if dist_soporte and dist_resistencia:
        rango_total = dist_soporte + dist_resistencia
        posicion_rango = round((dist_resistencia / rango_total) * 100)
        if posicion_rango < 30:
            contexto = "CERCA_RESISTENCIA_precaución"
        elif posicion_rango > 70:
            contexto = "CERCA_SOPORTE_oportunidad"
        else:
            contexto = "ZONA_MEDIA_esperar_confirmacion"
    else:
        posicion_rango = 50
        contexto = "SIN_REFERENCIA_clara"

    return {
        "precio_actual":        precio_actual,
        "zonas_demanda":        zonas_demanda,
        "zonas_oferta":         zonas_oferta,
        "soporte_cercano":      soporte_cercano,
        "resistencia_cercana":  resistencia_cercana,
        "dist_soporte_pct":     dist_soporte,
        "dist_resistencia_pct": dist_resistencia,
        "posicion_rango_pct":   posicion_rango,
        "contexto":             contexto,
    }

def calcular_niveles_fibonacci(precio_min: float, precio_max: float) -> dict:
    rango = precio_max - precio_min
    niveles = {
        "0.0":   round(precio_max, 4),
        "0.236": round(precio_max - rango * 0.236, 4),
        "0.382": round(precio_max - rango * 0.382, 4),
        "0.5":   round(precio_max - rango * 0.5,   4),
        "0.618": round(precio_max - rango * 0.618, 4),
        "0.786": round(precio_max - rango * 0.786, 4),
        "1.0":   round(precio_min, 4),
    }
    return niveles

def analizar_niveles_completo(simbolo: str) -> dict:
    print(f"[agente_niveles] Analizando {simbolo} diario...")
    df_diario = obtener_velas_binance(simbolo, intervalo="1d", limite=365)

    print(f"[agente_niveles] Analizando {simbolo} 4h...")
    df_4h = obtener_velas_binance(simbolo, intervalo="4h", limite=200)

    zonas_diario = detectar_zonas_sd(df_diario)
    zonas_4h     = detectar_zonas_sd(df_4h)

    # Fibonacci del ultimo swing
    if not df_diario.empty:
        highs_30d = df_diario["high"].values[-30:]
        lows_30d  = df_diario["low"].values[-30:]
        fib = calcular_niveles_fibonacci(float(np.min(lows_30d)), float(np.max(highs_30d)))
    else:
        fib = {}

    precio_actual = zonas_diario.get("precio_actual", 0)

    # Fibonacci nivel mas cercano
    fib_cercano = None
    if fib and precio_actual:
        fib_cercano = min(fib.items(), key=lambda x: abs(x[1] - precio_actual))

    return {
        "simbolo":         simbolo,
        "precio_actual":   precio_actual,
        "zonas_diario":    zonas_diario,
        "zonas_4h":        zonas_4h,
        "fibonacci":       fib,
        "fib_cercano":     fib_cercano,
        "timestamp":       datetime.now().strftime("%H:%M:%S"),
    }

def obtener_reporte_niveles(activos: list = None) -> str:
    if activos is None:
        activos = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
    lineas = []
    for simbolo in activos:
        r = analizar_niveles_completo(simbolo)
        zd = r["zonas_diario"]
        lineas.append(
            f"{simbolo}: precio={r['precio_actual']} | "
            f"contexto={zd.get('contexto','N/A')} | "
            f"dist_soporte={zd.get('dist_soporte_pct','N/A')}% | "
            f"dist_resistencia={zd.get('dist_resistencia_pct','N/A')}% | "
            f"fib_cercano={r.get('fib_cercano','N/A')}"
        )
    return "\n".join(lineas)