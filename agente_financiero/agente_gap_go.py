# agente_financiero/agente_gap_go.py
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from agente_financiero.cache_mercado import obtener_velas

ACTIVOS_ACCIONES = ["AAPL", "NVDA", "MSFT", "TSLA", "SPY", "QQQ", "AMZN", "GOOGL", "META"]
ACTIVOS_CRYPTO   = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

def detectar_gap_accion(simbolo: str) -> dict:
    try:
        ticker = yf.Ticker(simbolo)
        df     = ticker.history(period="5d", interval="1d")
        df_hoy = ticker.history(period="1d", interval="1m")

        if df.empty or len(df) < 2:
            return {"simbolo": simbolo, "error": "Sin datos"}

        cierre_ayer  = float(df["Close"].iloc[-2])
        apertura_hoy = float(df_hoy["Open"].iloc[0]) if not df_hoy.empty else float(df["Open"].iloc[-1])
        precio_actual = float(df_hoy["Close"].iloc[-1]) if not df_hoy.empty else float(df["Close"].iloc[-1])
        volumen_hoy  = int(df_hoy["Volume"].sum()) if not df_hoy.empty else 0
        volumen_prom = int(df["Volume"].mean())

        gap_pct = round(((apertura_hoy - cierre_ayer) / cierre_ayer) * 100, 3)
        ratio_volumen = round(volumen_hoy / volumen_prom, 2) if volumen_prom > 0 else 0

        # Clasificacion del gap
        if abs(gap_pct) < 0.5:
            tipo_gap = "SIN_GAP"
            señal    = "ESPERAR"
            fuerza   = "ninguna"
        elif gap_pct >= 2.0 and ratio_volumen >= 1.5:
            tipo_gap = "GAP_ALCISTA_FUERTE"
            señal    = "COMPRAR"
            fuerza   = "muy_alta"
        elif gap_pct >= 1.0:
            tipo_gap = "GAP_ALCISTA"
            señal    = "COMPRAR"
            fuerza   = "alta"
        elif gap_pct <= -2.0 and ratio_volumen >= 1.5:
            tipo_gap = "GAP_BAJISTA_FUERTE"
            señal    = "VENDER"
            fuerza   = "muy_alta"
        elif gap_pct <= -1.0:
            tipo_gap = "GAP_BAJISTA"
            señal    = "VENDER"
            fuerza   = "alta"
        else:
            tipo_gap = "GAP_PEQUEÑO"
            señal    = "ESPERAR"
            fuerza   = "baja"

        # Verifica si el gap se está llenando o continuando
        if señal == "COMPRAR":
            continuacion = precio_actual > apertura_hoy
            estado = "CONTINUANDO" if continuacion else "LLENANDO_GAP"
        elif señal == "VENDER":
            continuacion = precio_actual < apertura_hoy
            estado = "CONTINUANDO" if continuacion else "LLENANDO_GAP"
        else:
            estado = "NEUTRAL"

        # Stop loss y take profit
        rango_gap = abs(apertura_hoy - cierre_ayer)
        if señal == "COMPRAR":
            sl  = round(apertura_hoy - rango_gap * 0.5, 4)
            tp1 = round(apertura_hoy + rango_gap * 1.5, 4)
            tp2 = round(apertura_hoy + rango_gap * 3.0, 4)
        elif señal == "VENDER":
            sl  = round(apertura_hoy + rango_gap * 0.5, 4)
            tp1 = round(apertura_hoy - rango_gap * 1.5, 4)
            tp2 = round(apertura_hoy - rango_gap * 3.0, 4)
        else:
            sl = tp1 = tp2 = 0

        return {
            "simbolo":       simbolo,
            "tipo":          "accion",
            "cierre_ayer":   round(cierre_ayer, 4),
            "apertura_hoy":  round(apertura_hoy, 4),
            "precio_actual": round(precio_actual, 4),
            "gap_pct":       gap_pct,
            "tipo_gap":      tipo_gap,
            "señal":         señal,
            "fuerza":        fuerza,
            "estado":        estado,
            "ratio_volumen": ratio_volumen,
            "stop_loss":     sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "timestamp":     datetime.now().strftime("%H:%M:%S"),
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def detectar_gap_crypto(simbolo: str) -> dict:
    try:
        df = obtener_velas(simbolo, "1h", 48)
        if df.empty or len(df) < 24:
            return {"simbolo": simbolo, "error": "Sin datos"}

        # Para crypto usamos gaps entre sesiones (cada 8 horas)
        closes = df["close"].values
        opens  = df["open"].values

        # Gap entre cierre de vela anterior y apertura actual
        gaps = []
        for i in range(1, len(df)):
            gap = ((opens[i] - closes[i-1]) / closes[i-1]) * 100
            gaps.append(gap)

        gap_actual = gaps[-1] if gaps else 0
        gap_max_24h = max(abs(g) for g in gaps[-24:]) if gaps else 0

        precio_actual = float(df["close"].iloc[-1])
        vwap_simple   = float(df["close"].tail(24).mean())

        if abs(gap_actual) >= 1.5:
            tipo_gap = "GAP_CRYPTO_FUERTE"
            señal    = "COMPRAR" if gap_actual > 0 else "VENDER"
            fuerza   = "alta"
        elif abs(gap_actual) >= 0.8:
            tipo_gap = "GAP_CRYPTO"
            señal    = "COMPRAR" if gap_actual > 0 else "VENDER"
            fuerza   = "media"
        else:
            tipo_gap = "SIN_GAP"
            señal    = "ESPERAR"
            fuerza   = "ninguna"

        atr = float(np.mean([abs(float(df["high"].iloc[i]) - float(df["low"].iloc[i])) for i in range(-14, 0)]))

        sl  = round(precio_actual - atr * 2, 4) if señal == "COMPRAR" else round(precio_actual + atr * 2, 4)
        tp1 = round(precio_actual + atr * 3, 4) if señal == "COMPRAR" else round(precio_actual - atr * 3, 4)
        tp2 = round(precio_actual + atr * 5, 4) if señal == "COMPRAR" else round(precio_actual - atr * 5, 4)

        return {
            "simbolo":       simbolo,
            "tipo":          "crypto",
            "gap_pct":       round(gap_actual, 3),
            "gap_max_24h":   round(gap_max_24h, 3),
            "tipo_gap":      tipo_gap,
            "señal":         señal,
            "fuerza":        fuerza,
            "precio_actual": round(precio_actual, 4),
            "stop_loss":     sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "timestamp":     datetime.now().strftime("%H:%M:%S"),
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def ejecutar_gap_go() -> list:
    resultados = []
    print("[agente_gap] Detectando gaps en acciones...")
    for simbolo in ACTIVOS_ACCIONES:
        r = detectar_gap_accion(simbolo)
        if "error" not in r:
            resultados.append(r)

    print("[agente_gap] Detectando gaps en crypto...")
    for simbolo in ACTIVOS_CRYPTO:
        r = detectar_gap_crypto(simbolo)
        if "error" not in r:
            resultados.append(r)

    return resultados

def obtener_reporte_gap() -> str:
    resultados = ejecutar_gap_go()
    lineas = []
    for r in resultados:
        if r.get("señal") != "ESPERAR":
            lineas.append(
                f"{r['simbolo']}: {r['señal']} ({r['fuerza']}) | "
                f"gap={r['gap_pct']}% | tipo={r['tipo_gap']} | "
                f"SL={r['stop_loss']} TP1={r['take_profit_1']}"
            )
    return "\n".join(lineas) if lineas else "Sin gaps significativos detectados"