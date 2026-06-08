# agente_financiero/agente_velas.py
import asyncio
import numpy as np
import pandas as pd
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from nucleo.cliente_ia import chat

ACTIVOS_CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

def obtener_velas_binance(simbolo: str, intervalo: str = "5m", limite: int = 100) -> pd.DataFrame:
    try:
        from agente_financiero.cache_mercado import obtener_velas
        return obtener_velas(simbolo, intervalo, limite)
    except Exception as e:
        print(f"[agente_velas] Error cache {simbolo}: {e}")
        return pd.DataFrame()

def detectar_patrones_velas(df: pd.DataFrame) -> list:
    if df.empty or len(df) < 10:
        return []
    patrones = []
    opens  = df["open"].values
    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values

    for i in range(2, len(df)):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        o1, c1     = opens[i-1], closes[i-1]
        o2, c2     = opens[i-2], closes[i-2]
        cuerpo     = abs(c - o)
        rango      = h - l if h - l > 0 else 0.0001

        if cuerpo / rango < 0.1:
            patrones.append({"vela": i, "patron": "DOJI", "señal": "indecision", "fuerza": "media"})
        if c > o and (l - min(o,c)) >= 2 * cuerpo and (h - max(o,c)) <= cuerpo * 0.3:
            patrones.append({"vela": i, "patron": "MARTILLO", "señal": "alcista", "fuerza": "alta"})
        if c < o and (h - max(o,c)) >= 2 * cuerpo and (min(o,c) - l) <= cuerpo * 0.3:
            patrones.append({"vela": i, "patron": "ESTRELLA_FUGAZ", "señal": "bajista", "fuerza": "alta"})
        if c2 < o2 and c > o and c > o2 and o < c2:
            patrones.append({"vela": i, "patron": "ENVOLVENTE_ALCISTA", "señal": "alcista", "fuerza": "muy_alta"})
        if c2 > o2 and c < o and c < o2 and o > c2:
            patrones.append({"vela": i, "patron": "ENVOLVENTE_BAJISTA", "señal": "bajista", "fuerza": "muy_alta"})

    return patrones[-10:] if len(patrones) > 10 else patrones

def calcular_niveles(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    closes = df["close"].values
    highs  = df["high"].values
    lows   = df["low"].values

    resistencia = np.max(highs[-20:])
    soporte     = np.min(lows[-20:])
    precio      = closes[-1]

    deltas    = np.diff(closes[-15:])
    ganancias = np.where(deltas > 0, deltas, 0)
    perdidas  = np.where(deltas < 0, -deltas, 0)
    avg_gan   = np.mean(ganancias) if np.mean(ganancias) > 0 else 0.0001
    avg_per   = np.mean(perdidas)  if np.mean(perdidas)  > 0 else 0.0001
    rsi       = 100 - (100 / (1 + avg_gan / avg_per))

    ma5  = np.mean(closes[-5:])
    ma20 = np.mean(closes[-20:])

    return {
        "precio":                    round(precio, 4),
        "soporte":                   round(soporte, 4),
        "resistencia":               round(resistencia, 4),
        "rsi_rapido":                round(rsi, 1),
        "tendencia_corto":           "alcista" if ma5 > ma20 else "bajista",
        "distancia_resistencia_pct": round(((resistencia - precio) / precio) * 100, 2),
        "distancia_soporte_pct":     round(((precio - soporte)     / precio) * 100, 2),
    }

def analizar_micro_movimientos(simbolo: str) -> dict:
    """
    Analiza velas de 1 minuto para detectar micro movimientos.
    Complementa el análisis de 5M con señales de muy corto plazo.
    """
    try:
        df_1m = obtener_velas_binance(simbolo, "1m", 30)
        if df_1m.empty:
            return {"disponible": False}

        closes  = df_1m["close"].values
        volumes = df_1m["volume"].values
        highs   = df_1m["high"].values
        lows    = df_1m["low"].values

        # Momentum de los últimos 5 minutos
        cambio_5m   = ((closes[-1] - closes[-6]) / closes[-6]) * 100 if len(closes) >= 6 else 0
        cambio_1m   = ((closes[-1] - closes[-2]) / closes[-2]) * 100 if len(closes) >= 2 else 0

        # Volumen relativo — ¿está aumentando?
        vol_reciente  = np.mean(volumes[-5:])
        vol_promedio  = np.mean(volumes[-20:])
        vol_relativo  = vol_reciente / vol_promedio if vol_promedio > 0 else 1.0

        # Rango de la última vela vs promedio
        rango_actual  = highs[-1] - lows[-1]
        rango_promedio= np.mean(highs[-20:] - lows[-20:])
        rango_relativo= rango_actual / rango_promedio if rango_promedio > 0 else 1.0

        # Señal micro
        señal_micro = "NEUTRAL"
        if cambio_5m > 0.5 and vol_relativo > 1.5:
            señal_micro = "MICRO_ALCISTA — momentum + volumen confirmando"
        elif cambio_5m < -0.5 and vol_relativo > 1.5:
            señal_micro = "MICRO_BAJISTA — momentum + volumen confirmando"
        elif vol_relativo > 2.5:
            señal_micro = "SPIKE_VOLUMEN — movimiento fuerte inminente"
        elif rango_relativo > 2.0:
            señal_micro = "EXPANSION_RANGO — volatilidad aumentando"

        return {
            "disponible":    True,
            "cambio_1m_pct": round(cambio_1m, 3),
            "cambio_5m_pct": round(cambio_5m, 3),
            "vol_relativo":  round(vol_relativo, 2),
            "rango_relativo": round(rango_relativo, 2),
            "señal_micro":   señal_micro,
            "precio_actual": round(closes[-1], 4),
        }
    except Exception as e:
        return {"disponible": False, "error": str(e)}

async def analizar_oportunidades() -> dict:
    oportunidades = []
    alertas       = []

    for simbolo in ACTIVOS_CRYPTO:
        print(f"[agente_velas] Analizando {simbolo}...")
        df = obtener_velas_binance(simbolo)
        if df.empty:
            continue

        patrones         = detectar_patrones_velas(df)
        niveles          = calcular_niveles(df)
        micro            = analizar_micro_movimientos(simbolo)
        señales_alcistas = [p for p in patrones if p["señal"] == "alcista"]
        señales_bajistas = [p for p in patrones if p["señal"] == "bajista"]

        # Boost de confianza si micro confirma
        micro_confirma_alcista = micro.get("disponible") and "MICRO_ALCISTA" in micro.get("señal_micro","")
        micro_confirma_bajista = micro.get("disponible") and "MICRO_BAJISTA" in micro.get("señal_micro","")
        spike_volumen          = micro.get("disponible") and "SPIKE_VOLUMEN" in micro.get("señal_micro","")

        if señales_alcistas and niveles.get("rsi_rapido", 50) < 65:
            oportunidades.append({
                "simbolo":               simbolo,
                "tipo":                  "COMPRA",
                "precio":                niveles.get("precio"),
                "patrones":              [p["patron"] for p in señales_alcistas],
                "rsi":                   niveles.get("rsi_rapido"),
                "resistencia":           niveles.get("resistencia"),
                "distancia_resistencia": niveles.get("distancia_resistencia_pct"),
                "micro_confirma":        micro_confirma_alcista,
                "vol_relativo":          micro.get("vol_relativo", 1.0),
                "cambio_5m":             micro.get("cambio_5m_pct", 0),
                "spike_volumen":         spike_volumen,
            })
        if señales_bajistas and niveles.get("rsi_rapido", 50) > 35:
            alertas.append({
                "simbolo":        simbolo,
                "tipo":           "VENTA",
                "precio":         niveles.get("precio"),
                "patrones":       [p["patron"] for p in señales_bajistas],
                "rsi":            niveles.get("rsi_rapido"),
                "micro_confirma": micro_confirma_bajista,
                "vol_relativo":   micro.get("vol_relativo", 1.0),
            })

    resumen_opor = "\n".join([
        f"OPORTUNIDAD {o['simbolo']}: {o['tipo']} | precio={o['precio']} | "
        f"patrones={o['patrones']} | RSI={o['rsi']} | "
        f"dist_resistencia={o['distancia_resistencia']}% | "
        f"micro={'CONFIRMA' if o['micro_confirma'] else 'neutro'} | "
        f"vol_rel={o['vol_relativo']}x | cambio_5m={o['cambio_5m']}%"
        f"{' | ⚡ SPIKE_VOLUMEN' if o.get('spike_volumen') else ''}"
        for o in oportunidades
    ]) or "Sin oportunidades claras"

    resumen_alertas = "\n".join([
        f"ALERTA {a['simbolo']}: {a['tipo']} | precio={a['precio']} | "
        f"patrones={a['patrones']} | "
        f"micro={'CONFIRMA' if a['micro_confirma'] else 'neutro'} | "
        f"vol_rel={a['vol_relativo']}x"
        for a in alertas
    ]) or "Sin alertas"

    print("[agente_velas] Generando recomendaciones con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"OPORTUNIDADES:\n{resumen_opor}\n\nALERTAS:\n{resumen_alertas}"}],
        system="""Eres un trader experto en velas japonesas analizando crypto (BTC ETH SOL BNB).
Analiza las oportunidades considerando patrones de velas en 5M Y confirmación de micro movimientos en 1M.
Prioriza señales donde el campo micro='CONFIRMA' o hay SPIKE_VOLUMEN — son de mayor probabilidad.
Para cada señal entrega: precio entrada, stop loss (ATR x2), take profit 1 (ratio 2:1), take profit 2 (ratio 3:1), confianza %.
Aumenta la confianza 10% si micro confirma, 15% si hay spike de volumen.
Si no hay señales claras responde: SIN_SEÑALES_VELAS
Responde en español conciso.""",
        max_tokens=600,
        agente="agente_velas"
    )

    return {
        "oportunidades":   oportunidades,
        "alertas":         alertas,
        "recomendaciones": respuesta["texto"],
        "timestamp":       datetime.now().strftime("%H:%M:%S"),
    }

async def obtener_reporte_velas() -> str:
    resultado = await analizar_oportunidades()
    return resultado.get("recomendaciones", "Sin señales de velas")
