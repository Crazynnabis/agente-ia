# agente_financiero/digestor_acciones.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, time
import pytz
from nucleo.cliente_ia import chat

ACTIVOS_ACCIONES = ["AAPL", "NVDA", "MSFT", "TSLA", "SPY", "QQQ"]

def es_horario_mercado() -> bool:
    tz    = pytz.timezone("America/New_York")
    ahora = datetime.now(tz)
    if ahora.weekday() >= 5:
        return False
    apertura = time(9, 30)
    cierre   = time(16, 0)
    return apertura <= ahora.time() <= cierre

def obtener_datos_accion(simbolo: str, periodo: str = "5d", intervalo: str = "5m") -> pd.DataFrame:
    try:
        ticker = yf.Ticker(simbolo)
        df     = ticker.history(period=periodo, interval=intervalo)
        if df.empty:
            return pd.DataFrame()
        df.index = df.index.tz_convert("America/New_York")
        return df
    except Exception as e:
        print(f"[digestor_acciones] Error {simbolo}: {e}")
        return pd.DataFrame()

def calcular_indicadores_accion(df: pd.DataFrame) -> dict:
    if df.empty or len(df) < 20:
        return {}

    closes  = df["Close"].values
    highs   = df["High"].values
    lows    = df["Low"].values
    volumes = df["Volume"].values
    precio  = float(closes[-1])

    # RSI
    deltas    = np.diff(closes[-15:])
    ganancias = np.where(deltas > 0, deltas, 0)
    perdidas  = np.where(deltas < 0, -deltas, 0)
    avg_gan   = np.mean(ganancias) if np.mean(ganancias) > 0 else 0.0001
    avg_per   = np.mean(perdidas)  if np.mean(perdidas)  > 0 else 0.0001
    rsi       = round(100 - (100 / (1 + avg_gan / avg_per)), 1)

    # VWAP
    precio_tipico = (df["High"] + df["Low"] + df["Close"]) / 3
    vwap          = float((precio_tipico * df["Volume"]).cumsum().iloc[-1] / df["Volume"].cumsum().iloc[-1])

    # MA
    ma20  = round(float(np.mean(closes[-20:])), 4)
    ma50  = round(float(np.mean(closes[-50:])), 4) if len(closes) >= 50 else ma20

    # ATR
    trs  = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1, min(15, len(closes)))]
    atr  = round(float(np.mean(trs)), 4)

    # Volumen vs promedio
    vol_actual = float(volumes[-1])
    vol_prom   = float(np.mean(volumes[-20:]))
    ratio_vol  = round(vol_actual / vol_prom, 2) if vol_prom > 0 else 1.0

    # Cambios
    cambio_1d  = round(((precio - closes[-2]) / closes[-2]) * 100, 3) if len(closes) > 1 else 0
    cambio_5d  = round(((precio - closes[-min(len(closes),78)]) / closes[-min(len(closes),78)]) * 100, 3)

    return {
        "precio":      round(precio, 4),
        "rsi":         rsi,
        "vwap":        round(vwap, 4),
        "ma20":        ma20,
        "ma50":        ma50,
        "atr":         atr,
        "ratio_vol":   ratio_vol,
        "cambio_1d":   cambio_1d,
        "cambio_5d":   cambio_5d,
        "sl_largo":    round(precio - atr * 2.5, 4),
        "sl_corto":    round(precio + atr * 2.5, 4),
        "tp1_largo":   round(precio + atr * 5.0, 4),
        "tp1_corto":   round(precio - atr * 5.0, 4),
        "tp2_largo":   round(precio + atr * 7.5, 4),
        "tp2_corto":   round(precio - atr * 7.5, 4),
    }

def analizar_señal_accion(simbolo: str, ind: dict) -> dict:
    if not ind:
        return {"simbolo": simbolo, "señal_final": "ESPERAR", "confluencia": "BAJA", "confianza": 0}

    precio = ind["precio"]
    rsi    = ind["rsi"]
    vwap   = ind["vwap"]
    ma20   = ind["ma20"]
    ma50   = ind["ma50"]

    puntos_compra = 0
    puntos_venta  = 0

    if rsi < 35:             puntos_compra += 2
    elif rsi < 45:           puntos_compra += 1
    if rsi > 65:             puntos_venta  += 2
    elif rsi > 55:           puntos_venta  += 1
    if precio > vwap:        puntos_compra += 1
    else:                    puntos_venta  += 1
    if ma20 > ma50:          puntos_compra += 1
    else:                    puntos_venta  += 1
    if ind["ratio_vol"] > 1.5:
        if ind["cambio_1d"] > 0: puntos_compra += 2
        else:                    puntos_venta  += 2
    if ind["cambio_1d"] > 1.5:  puntos_compra += 1
    if ind["cambio_1d"] < -1.5: puntos_venta  += 1

    total     = puntos_compra + puntos_venta
    confianza = round((max(puntos_compra, puntos_venta) / max(total, 1)) * 100)

    if puntos_compra >= 5:
        señal_final = "COMPRAR"
        confluencia = "MUY_ALTA"
        confianza   = min(confianza + 20, 99)
    elif puntos_compra >= 3:
        señal_final = "COMPRAR"
        confluencia = "ALTA"
        confianza   = min(confianza + 10, 99)
    elif puntos_venta >= 5:
        señal_final = "VENDER"
        confluencia = "MUY_ALTA"
        confianza   = min(confianza + 20, 99)
    elif puntos_venta >= 3:
        señal_final = "VENDER"
        confluencia = "ALTA"
        confianza   = min(confianza + 10, 99)
    else:
        señal_final = "ESPERAR"
        confluencia = "BAJA"
        confianza   = max(confianza - 20, 10)

    return {
        "simbolo":      simbolo,
        "precio":       ind["precio"],
        "señal_final":  señal_final,
        "confluencia":  confluencia,
        "confianza":    confianza,
        "rsi":          rsi,
        "vwap":         vwap,
        "ma20":         ma20,
        "ma50":         ma50,
        "cambio_1d":    ind["cambio_1d"],
        "cambio_5d":    ind["cambio_5d"],
        "ratio_vol":    ind["ratio_vol"],
        "stop_loss":    ind["sl_largo"] if señal_final == "COMPRAR" else ind["sl_corto"],
        "take_profit_1":ind["tp1_largo"] if señal_final == "COMPRAR" else ind["tp1_corto"],
        "take_profit_2":ind["tp2_largo"] if señal_final == "COMPRAR" else ind["tp2_corto"],
        "atr":          ind["atr"],
    }

async def ejecutar_ciclo_acciones() -> dict:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[digestor_acciones] Ciclo acciones {timestamp}")

    if not es_horario_mercado():
        print("[digestor_acciones] Mercado USA cerrado — usando datos del cierre")

    resultados = []
    for simbolo in ACTIVOS_ACCIONES:
        print(f"[digestor_acciones] Analizando {simbolo}...")
        df  = obtener_datos_accion(simbolo, periodo="5d", intervalo="5m")
        ind = calcular_indicadores_accion(df)
        res = analizar_señal_accion(simbolo, ind)
        resultados.append(res)

    señales_fuertes = [
        r for r in resultados
        if r["confluencia"] in ["ALTA", "MUY_ALTA"] and r["confianza"] >= 80
    ]

    resumen = "\n".join([
        f"{r['simbolo']}: {r['señal_final']} | {r['confluencia']} | conf={r['confianza']}% | "
        f"precio=${r['precio']} | RSI={r['rsi']} | VWAP={r['vwap']} | "
        f"MA20={r['ma20']} MA50={r['ma50']} | vol={r['ratio_vol']}x | "
        f"1d={r['cambio_1d']}% 5d={r['cambio_5d']}% | "
        f"SL={r['stop_loss']} TP1={r['take_profit_1']}"
        for r in resultados
    ])

    print("[digestor_acciones] Generando analisis con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"ANALISIS ACCIONES USA:\n{resumen}"}],
        system="""Eres el digestor de acciones de un sistema de trading profesional.
Recibes datos tecnicos de acciones NYSE/NASDAQ: RSI, VWAP, MA20/50, volumen y cambio de precio.
Solo opera acciones cuando el mercado USA está abierto (9:30-16:00 ET).
Entrega decisiones SOLO para señales con confluencia ALTA o MUY_ALTA y confianza mayor a 80%.
Formato:
DECISION_ACCION_N:
- ACCION: COMPRAR o VENDER
- SIMBOLO: nombre exacto
- PRECIO_ENTRADA: numero
- STOP_LOSS: numero
- TAKE_PROFIT_1: numero (ratio 2:1)
- TAKE_PROFIT_2: numero (ratio 3:1)
- CONFIANZA: porcentaje
- RAZON: una oracion
- HORIZONTE: intradía o swing
Si no hay señales: SIN_SEÑALES_ACCIONES
Responde en español sin texto adicional.""",
        max_tokens=600
    )

    return {
        "timestamp":       timestamp,
        "mercado_abierto": es_horario_mercado(),
        "resultados":      resultados,
        "señales_fuertes": señales_fuertes,
        "decisiones":      respuesta["texto"],
        "modelo":          respuesta["modelo"],
    }