# agente_financiero/agente_orb.py
# Opening Range Breakout — estrategia de primeros 5 minutos
import requests
import numpy as np
import pandas as pd
import json
import os
from datetime import datetime, timedelta
import yfinance as yf
from agente_financiero.cache_mercado import obtener_velas

ACTIVOS_ACCIONES = ["AAPL", "NVDA", "MSFT", "TSLA", "SPY", "QQQ", "AMZN", "GOOGL"]
ACTIVOS_CRYPTO   = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

# Archivo de historial ORB
ORB_HISTORIAL = os.path.join(os.path.dirname(__file__), '..', 'logs', 'orb_historial.jsonl')
os.makedirs(os.path.dirname(ORB_HISTORIAL), exist_ok=True)

def obtener_rango_apertura_crypto(simbolo: str, minutos: int = 5) -> dict:
    try:
        df = obtener_velas(simbolo, "1m", 30)
        if df.empty:
            return {}

        ahora  = datetime.utcnow()
        inicio = ahora.replace(second=0, microsecond=0) - timedelta(minutes=minutos)

        df_orb = df[df["timestamp"] >= pd.Timestamp(inicio, tz="UTC")]
        if df_orb.empty or len(df_orb) < 2:
            df_orb = df.tail(minutos)

        orb_high  = float(df_orb["high"].max())
        orb_low   = float(df_orb["low"].min())
        orb_rango = round(orb_high - orb_low, 4)
        precio    = float(df["close"].iloc[-1])
        volumen   = float(df_orb["volume"].sum())

        estado = "DENTRO_RANGO"
        señal  = "ESPERAR"
        if precio > orb_high:
            estado = "RUPTURA_ALCISTA"
            señal  = "COMPRAR"
        elif precio < orb_low:
            estado = "RUPTURA_BAJISTA"
            señal  = "VENDER"
        elif precio > (orb_high + orb_low) / 2:
            estado = "SESGO_ALCISTA"
        else:
            estado = "SESGO_BAJISTA"

        atr_estimado = orb_rango * 0.5
        sl  = round(orb_low - atr_estimado, 4)  if señal == "COMPRAR" else round(orb_high + atr_estimado, 4)
        tp1 = round(precio + orb_rango * 2, 4)  if señal == "COMPRAR" else round(precio - orb_rango * 2, 4)
        tp2 = round(precio + orb_rango * 3, 4)  if señal == "COMPRAR" else round(precio - orb_rango * 3, 4)

        return {
            "simbolo":    simbolo,
            "tipo":       "crypto",
            "precio":     precio,
            "orb_high":   round(orb_high, 4),
            "orb_low":    round(orb_low, 4),
            "orb_rango":  orb_rango,
            "orb_rango_pct": round((orb_rango / precio) * 100, 3),
            "volumen_orb": round(volumen, 2),
            "estado":     estado,
            "señal":      señal,
            "stop_loss":  sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "timestamp":  datetime.utcnow().strftime("%H:%M:%S"),
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def obtener_rango_apertura_accion(simbolo: str) -> dict:
    try:
        ticker = yf.Ticker(simbolo)
        df = ticker.history(period="1d", interval="1m")
        if df.empty:
            return {"simbolo": simbolo, "error": "Sin datos"}

        # Primeros 5 minutos desde apertura 9:30
        df.index = df.index.tz_convert("America/New_York")
        apertura = df.index[0].replace(hour=9, minute=30, second=0)
        cierre_orb = apertura + timedelta(minutes=5)

        df_orb = df[(df.index >= apertura) & (df.index < cierre_orb)]
        if df_orb.empty:
            df_orb = df.head(5)

        orb_high  = float(df_orb["High"].max())
        orb_low   = float(df_orb["Low"].min())
        orb_rango = round(orb_high - orb_low, 4)
        precio    = float(df["Close"].iloc[-1])
        volumen   = float(df_orb["Volume"].sum())

        estado = "DENTRO_RANGO"
        señal  = "ESPERAR"
        if precio > orb_high * 1.001:
            estado = "RUPTURA_ALCISTA"
            señal  = "COMPRAR"
        elif precio < orb_low * 0.999:
            estado = "RUPTURA_BAJISTA"
            señal  = "VENDER"

        atr_estimado = orb_rango * 0.5
        sl  = round(orb_low  - atr_estimado, 4) if señal == "COMPRAR" else round(orb_high + atr_estimado, 4)
        tp1 = round(precio + orb_rango * 2, 4)  if señal == "COMPRAR" else round(precio - orb_rango * 2, 4)
        tp2 = round(precio + orb_rango * 3, 4)  if señal == "COMPRAR" else round(precio - orb_rango * 3, 4)

        hora_actual = datetime.now().strftime("%H:%M")
        en_sesion   = "09:30" <= hora_actual <= "16:00"

        return {
            "simbolo":       simbolo,
            "tipo":          "accion",
            "precio":        precio,
            "orb_high":      round(orb_high, 4),
            "orb_low":       round(orb_low, 4),
            "orb_rango":     orb_rango,
            "orb_rango_pct": round((orb_rango / precio) * 100, 3),
            "volumen_orb":   round(volumen, 0),
            "estado":        estado,
            "señal":         señal,
            "stop_loss":     sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "en_sesion":     en_sesion,
            "timestamp":     datetime.now().strftime("%H:%M:%S"),
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def guardar_resultado_orb(resultado: dict):
    try:
        with open(ORB_HISTORIAL, "a", encoding="utf-8") as f:
            resultado["fecha"] = datetime.now().strftime("%Y-%m-%d")
            f.write(json.dumps(resultado) + "\n")
    except Exception as e:
        print(f"[agente_orb] Error guardando: {e}")

def analizar_historial_orb(simbolo: str, dias: int = 30) -> dict:
    if not os.path.exists(ORB_HISTORIAL):
        return {"simbolo": simbolo, "error": "Sin historial"}

    registros = []
    with open(ORB_HISTORIAL, "r", encoding="utf-8") as f:
        for linea in f:
            try:
                r = json.loads(linea)
                if r.get("simbolo") == simbolo and r.get("señal") != "ESPERAR":
                    registros.append(r)
            except:
                continue

    if not registros:
        return {"simbolo": simbolo, "historial": "Sin señales registradas"}

    señales_compra = [r for r in registros if r.get("señal") == "COMPRAR"]
    señales_venta  = [r for r in registros if r.get("señal") == "VENDER"]
    rango_promedio = np.mean([r.get("orb_rango_pct", 0) for r in registros])

    return {
        "simbolo":        simbolo,
        "total_señales":  len(registros),
        "compras":        len(señales_compra),
        "ventas":         len(señales_venta),
        "rango_promedio": round(rango_promedio, 3),
    }

def ejecutar_analisis_orb() -> list:
    resultados = []

    print("[agente_orb] Analizando crypto ORB...")
    for simbolo in ACTIVOS_CRYPTO:
        r = obtener_rango_apertura_crypto(simbolo)
        if "error" not in r:
            guardar_resultado_orb(r)
            resultados.append(r)

    print("[agente_orb] Analizando acciones ORB...")
    for simbolo in ACTIVOS_ACCIONES:
        r = obtener_rango_apertura_accion(simbolo)
        if "error" not in r:
            guardar_resultado_orb(r)
            resultados.append(r)

    return resultados

def obtener_reporte_orb() -> str:
    resultados = ejecutar_analisis_orb()
    lineas = []
    for r in resultados:
        if r.get("señal") != "ESPERAR":
            lineas.append(
                f"{r['simbolo']}: {r['señal']} | estado={r['estado']} | "
                f"rango={r['orb_rango_pct']}% | "
                f"SL={r['stop_loss']} TP1={r['take_profit_1']}"
            )
    return "\n".join(lineas) if lineas else "Sin rupturas ORB detectadas"