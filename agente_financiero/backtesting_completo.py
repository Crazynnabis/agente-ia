# agente_financiero/backtesting_completo.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import json
import numpy as np
import pandas as pd
import requests
from datetime import datetime, timedelta
from agente_financiero.cache_mercado import obtener_velas

ACTIVOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

def obtener_datos_historicos(simbolo: str, dias: int = 30) -> pd.DataFrame:
    try:
        limite = min(dias * 24 * 12, 1000)
        return obtener_velas(simbolo, "5m", limite)
    except Exception as e:
        print(f"[backtesting] Error {simbolo}: {e}")
        return pd.DataFrame()

def calcular_señales_historicas(df: pd.DataFrame) -> list:
    if df.empty or len(df) < 50:
        return []

    closes  = df["close"].values
    highs   = df["high"].values
    lows    = df["low"].values
    volumes = df["volume"].values
    señales = []

    for i in range(50, len(df) - 20):
        # RSI
        deltas    = np.diff(closes[i-14:i+1])
        ganancias = np.where(deltas > 0, deltas, 0)
        perdidas  = np.where(deltas < 0, -deltas, 0)
        avg_gan   = np.mean(ganancias) if np.mean(ganancias) > 0 else 0.0001
        avg_per   = np.mean(perdidas)  if np.mean(perdidas)  > 0 else 0.0001
        rsi       = 100 - (100 / (1 + avg_gan / avg_per))

        # VWAP
        precio_tipico = (highs[i] + lows[i] + closes[i]) / 3
        vwap_simple   = np.mean(closes[i-20:i])

        # MA
        ma20 = np.mean(closes[i-20:i])
        ma50 = np.mean(closes[i-50:i])

        # ATR
        atr = np.mean([highs[j] - lows[j] for j in range(i-14, i)])

        # Señal compuesta
        puntos_compra = 0
        puntos_venta  = 0

        if rsi < 35:             puntos_compra += 2
        if rsi > 65:             puntos_venta  += 2
        if closes[i] > vwap_simple: puntos_compra += 1
        if closes[i] < vwap_simple: puntos_venta  += 1
        if ma20 > ma50:          puntos_compra += 1
        if ma20 < ma50:          puntos_venta  += 1
        if volumes[i] > np.mean(volumes[i-20:i]) * 1.5:
            if closes[i] > closes[i-1]: puntos_compra += 1
            else:                        puntos_venta  += 1

        if puntos_compra >= 4:
            señales.append({
                "idx":    i,
                "accion": "COMPRAR",
                "precio": closes[i],
                "sl":     closes[i] - atr * 2.5,
                "tp1":    closes[i] + atr * 5.0,
                "tp2":    closes[i] + atr * 7.5,
                "puntos": puntos_compra,
            })
        elif puntos_venta >= 4:
            señales.append({
                "idx":    i,
                "accion": "VENDER",
                "precio": closes[i],
                "sl":     closes[i] + atr * 2.5,
                "tp1":    closes[i] - atr * 5.0,
                "tp2":    closes[i] - atr * 7.5,
                "puntos": puntos_venta,
            })

    return señales

def simular_operaciones(df: pd.DataFrame, señales: list) -> list:
    closes = df["close"].values
    highs  = df["high"].values
    lows   = df["low"].values
    resultados = []

    for señal in señales:
        idx    = señal["idx"]
        accion = señal["accion"]
        precio = señal["precio"]
        sl     = señal["sl"]
        tp1    = señal["tp1"]

        resultado = "TIEMPO"
        pnl_pct   = 0
        velas     = 0

        for j in range(idx + 1, min(idx + 50, len(df))):
            high  = highs[j]
            low   = lows[j]
            velas += 1

            if accion == "COMPRAR":
                if low <= sl:
                    pnl_pct   = round(((sl - precio) / precio) * 100, 3)
                    resultado = "STOP_LOSS"
                    break
                if high >= tp1:
                    pnl_pct   = round(((tp1 - precio) / precio) * 100, 3)
                    resultado = "TAKE_PROFIT"
                    break
            else:
                if high >= sl:
                    pnl_pct   = round(((precio - sl) / precio) * 100, 3)
                    resultado = "STOP_LOSS"
                    break
                if low <= tp1:
                    pnl_pct   = round(((precio - tp1) / precio) * 100, 3)
                    resultado = "TAKE_PROFIT"
                    break

        if resultado == "TIEMPO":
            precio_cierre = closes[min(idx + 50, len(df) - 1)]
            if accion == "COMPRAR":
                pnl_pct = round(((precio_cierre - precio) / precio) * 100, 3)
            else:
                pnl_pct = round(((precio - precio_cierre) / precio) * 100, 3)

        resultados.append({
            "accion":   accion,
            "precio":   precio,
            "resultado": resultado,
            "pnl_pct":  pnl_pct,
            "velas":    velas,
            "puntos":   señal["puntos"],
        })

    return resultados

def calcular_metricas(resultados: list, simbolo: str) -> dict:
    if not resultados:
        return {"simbolo": simbolo, "error": "Sin operaciones"}

    wins    = [r for r in resultados if r["resultado"] == "TAKE_PROFIT"]
    losses  = [r for r in resultados if r["resultado"] == "STOP_LOSS"]
    otros   = [r for r in resultados if r["resultado"] == "TIEMPO"]

    total    = len(resultados)
    win_rate = round(len(wins) / total * 100, 1) if total > 0 else 0

    pnl_wins   = sum(r["pnl_pct"] for r in wins)
    pnl_losses = sum(r["pnl_pct"] for r in losses)
    pnl_total  = sum(r["pnl_pct"] for r in resultados)

    profit_factor = round(abs(pnl_wins / pnl_losses), 2) if pnl_losses != 0 else float("inf")
    avg_win       = round(pnl_wins / len(wins), 3)   if wins   else 0
    avg_loss      = round(pnl_losses / len(losses), 3) if losses else 0
    velas_prom    = round(np.mean([r["velas"] for r in resultados]), 1)

    # Simulacion de capital $10,000 con 1% riesgo por op
    capital = 10000
    for r in resultados:
        riesgo = capital * 0.01
        if r["resultado"] == "TAKE_PROFIT":
            capital += riesgo * 2
        elif r["resultado"] == "STOP_LOSS":
            capital -= riesgo
        else:
            capital += riesgo * (r["pnl_pct"] / 2)

    return {
        "simbolo":          simbolo,
        "total_ops":        total,
        "wins":             len(wins),
        "losses":           len(losses),
        "otros":            len(otros),
        "win_rate":         win_rate,
        "pnl_total_pct":    round(pnl_total, 3),
        "profit_factor":    profit_factor,
        "avg_win_pct":      avg_win,
        "avg_loss_pct":     avg_loss,
        "velas_prom":       velas_prom,
        "capital_final":    round(capital, 2),
        "retorno_capital":  round((capital - 10000) / 10000 * 100, 2),
    }

def ejecutar_backtesting_completo(dias: int = 7) -> dict:
    print(f"\n=== BACKTESTING COMPLETO {dias} DIAS ===\n")
    todos_resultados = {}

    for simbolo in ACTIVOS:
        print(f"[backtesting] Procesando {simbolo}...")
        df      = obtener_datos_historicos(simbolo, dias)
        if df.empty:
            continue
        señales = calcular_señales_historicas(df)
        print(f"  Señales generadas: {len(señales)}")
        ops     = simular_operaciones(df, señales)
        metrics = calcular_metricas(ops, simbolo)
        todos_resultados[simbolo] = metrics

        print(f"  Win rate: {metrics.get('win_rate','N/A')}%")
        print(f"  Profit factor: {metrics.get('profit_factor','N/A')}")
        print(f"  Retorno: {metrics.get('retorno_capital','N/A')}%")
        print(f"  Capital final: ${metrics.get('capital_final','N/A')}")

    # Resumen global
    if todos_resultados:
        win_rates    = [v["win_rate"] for v in todos_resultados.values() if "error" not in v]
        retornos     = [v["retorno_capital"] for v in todos_resultados.values() if "error" not in v]
        pf_values    = [v["profit_factor"] for v in todos_resultados.values() if "error" not in v and v["profit_factor"] != float("inf")]

        print(f"\n=== RESUMEN GLOBAL ===")
        print(f"Win rate promedio: {round(np.mean(win_rates), 1)}%")
        print(f"Retorno promedio: {round(np.mean(retornos), 2)}%")
        print(f"Profit factor promedio: {round(np.mean(pf_values), 2)}")

    return todos_resultados