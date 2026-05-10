# agente_financiero/backtesting.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import json
import numpy as np
import pandas as pd
import requests
from datetime import datetime, timedelta

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')

def obtener_velas_historicas(simbolo: str, intervalo: str = "5m", dias: int = 7) -> pd.DataFrame:
    try:
        limite = min(dias * 24 * 12, 1000)
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
        print(f"[backtesting] Error: {e}")
        return pd.DataFrame()

def simular_operacion(df: pd.DataFrame, idx_entrada: int,
                      precio_entrada: float, stop_loss: float,
                      take_profit_1: float, accion: str) -> dict:
    if idx_entrada >= len(df) - 1:
        return {"resultado": "SIN_DATOS", "pnl_pct": 0}

    for i in range(idx_entrada + 1, len(df)):
        high  = df["high"].iloc[i]
        low   = df["low"].iloc[i]
        close = df["close"].iloc[i]

        if accion == "COMPRAR":
            if low <= stop_loss:
                pnl = ((stop_loss - precio_entrada) / precio_entrada) * 100
                return {"resultado": "STOP_LOSS", "pnl_pct": round(pnl, 3),
                        "velas_hasta_cierre": i - idx_entrada, "precio_cierre": stop_loss}
            if high >= take_profit_1:
                pnl = ((take_profit_1 - precio_entrada) / precio_entrada) * 100
                return {"resultado": "TAKE_PROFIT", "pnl_pct": round(pnl, 3),
                        "velas_hasta_cierre": i - idx_entrada, "precio_cierre": take_profit_1}

        elif accion == "VENDER":
            if high >= stop_loss:
                pnl = ((precio_entrada - stop_loss) / precio_entrada) * 100
                return {"resultado": "STOP_LOSS", "pnl_pct": round(pnl, 3),
                        "velas_hasta_cierre": i - idx_entrada, "precio_cierre": stop_loss}
            if low <= take_profit_1:
                pnl = ((precio_entrada - take_profit_1) / precio_entrada) * 100
                return {"resultado": "TAKE_PROFIT", "pnl_pct": round(pnl, 3),
                        "velas_hasta_cierre": i - idx_entrada, "precio_cierre": take_profit_1}

    # Cierre al final sin tocar SL ni TP
    precio_cierre = df["close"].iloc[-1]
    if accion == "COMPRAR":
        pnl = ((precio_cierre - precio_entrada) / precio_entrada) * 100
    else:
        pnl = ((precio_entrada - precio_cierre) / precio_entrada) * 100

    return {"resultado": "TIEMPO", "pnl_pct": round(pnl, 3),
            "velas_hasta_cierre": len(df) - idx_entrada, "precio_cierre": precio_cierre}

def backtest_señales_log(archivo_log: str = None) -> dict:
    if archivo_log is None:
        # Usa el log de hoy
        archivo_log = os.path.join(LOG_DIR, f"trading_{datetime.now().strftime('%Y%m%d')}.jsonl")

    if not os.path.exists(archivo_log):
        return {"error": f"No existe el archivo de log: {archivo_log}"}

    señales = []
    with open(archivo_log, "r", encoding="utf-8") as f:
        for linea in f:
            try:
                r = json.loads(linea)
                if r.get("tipo") == "SEÑAL" and r.get("aprobada_riesgo"):
                    señales.append(r)
            except:
                continue

    if not señales:
        return {"error": "Sin señales aprobadas en el log"}

    resultados = []
    for señal in señales[:20]:  # Limita a 20 para no saturar
        simbolo = señal.get("simbolo", "BTCUSDT")
        if not simbolo.endswith("USDT"):
            continue

        print(f"[backtesting] Simulando {señal['accion']} {simbolo}...")
        df = obtener_velas_historicas(simbolo, dias=1)
        if df.empty:
            continue

        idx = len(df) // 2  # Simula entrada a mitad del periodo
        resultado = simular_operacion(
            df, idx,
            float(señal.get("precio", 0)),
            float(señal.get("stop_loss", 0)),
            float(señal.get("take_profit_1", 0)),
            señal.get("accion", "COMPRAR")
        )
        resultado["simbolo"] = simbolo
        resultado["accion"]  = señal.get("accion")
        resultado["confianza"] = señal.get("confianza")
        resultados.append(resultado)

    return calcular_metricas_backtest(resultados)

def backtest_rapido(simbolo: str = "BTCUSDT", dias: int = 3) -> dict:
    print(f"[backtesting] Backtest rapido {simbolo} ultimos {dias} dias...")
    df = obtener_velas_historicas(simbolo, intervalo="5m", dias=dias)
    if df.empty:
        return {"error": "Sin datos"}

    closes = df["close"].values
    highs  = df["high"].values
    lows   = df["low"].values

    operaciones = []
    i = 20
    while i < len(df) - 50:
        # Señal simple: precio cruza MA20 hacia arriba
        ma20_actual  = np.mean(closes[i-20:i])
        ma20_anterior = np.mean(closes[i-21:i-1])
        precio = closes[i]

        if closes[i-1] < ma20_anterior and precio > ma20_actual:
            atr = np.mean([highs[j] - lows[j] for j in range(i-14, i)])
            sl  = precio - (atr * 2.5)
            tp1 = precio + (atr * 5.0)

            resultado = simular_operacion(df, i, precio, sl, tp1, "COMPRAR")
            resultado["simbolo"] = simbolo
            resultado["accion"]  = "COMPRAR"
            resultado["precio_entrada"] = precio
            operaciones.append(resultado)
            i += 20  # Espera antes de siguiente señal
        else:
            i += 1

    return calcular_metricas_backtest(operaciones)

def calcular_metricas_backtest(resultados: list) -> dict:
    if not resultados:
        return {"error": "Sin operaciones para analizar"}

    wins   = [r for r in resultados if r.get("resultado") == "TAKE_PROFIT"]
    losses = [r for r in resultados if r.get("resultado") == "STOP_LOSS"]
    otros  = [r for r in resultados if r.get("resultado") == "TIEMPO"]

    total    = len(resultados)
    win_rate = len(wins) / total * 100 if total > 0 else 0

    pnl_wins   = sum(r.get("pnl_pct", 0) for r in wins)
    pnl_losses = sum(r.get("pnl_pct", 0) for r in losses)
    pnl_otros  = sum(r.get("pnl_pct", 0) for r in otros)
    pnl_total  = pnl_wins + pnl_losses + pnl_otros

    avg_win  = pnl_wins  / len(wins)   if wins   else 0
    avg_loss = pnl_losses / len(losses) if losses else 0
    profit_factor = abs(pnl_wins / pnl_losses) if pnl_losses != 0 else float("inf")

    velas_promedio = np.mean([r.get("velas_hasta_cierre", 0) for r in resultados])

    return {
        "total_operaciones": total,
        "wins":              len(wins),
        "losses":            len(losses),
        "otros":             len(otros),
        "win_rate":          round(win_rate, 1),
        "pnl_total_pct":     round(pnl_total, 3),
        "avg_win_pct":       round(avg_win, 3),
        "avg_loss_pct":      round(avg_loss, 3),
        "profit_factor":     round(profit_factor, 2),
        "velas_promedio_cierre": round(velas_promedio, 1),
        "operaciones":       resultados,
    }