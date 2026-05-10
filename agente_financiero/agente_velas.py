# agente_financiero/agente_velas.py
import requests
import pandas as pd
import numpy as np
import ollama
from datetime import datetime

ACTIVOS_CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
ACTIVOS_ACCIONES = ["AAPL", "NVDA", "MSFT", "TSLA", "SPY"]

def obtener_velas_binance(simbolo: str, intervalo: str = "5m", limite: int = 100) -> pd.DataFrame:
    try:
        url = "https://api.binance.com/api/v3/klines"
        params = {"symbol": simbolo, "interval": intervalo, "limit": limite}
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        print(f"[agente_velas] Error Binance {simbolo}: {e}")
        return pd.DataFrame()

def detectar_patrones_velas(df: pd.DataFrame) -> list:
    if df.empty or len(df) < 10:
        return []

    patrones = []
    opens  = df["open"].values
    highs  = df["high"].values
    lows   = df["low"].values
    closes = df["close"].values
    vols   = df["volume"].values

    for i in range(2, len(df)):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        o1, h1, l1, c1 = opens[i-1], highs[i-1], lows[i-1], closes[i-1]
        o2, c2 = opens[i-2], closes[i-2]
        cuerpo = abs(c - o)
        rango  = h - l
        vol_prom = np.mean(vols[max(0,i-20):i])

        # Doji
        if rango > 0 and cuerpo / rango < 0.1:
            patrones.append({"vela": i, "patron": "DOJI", "señal": "indecision", "fuerza": "media"})

        # Martillo alcista
        if (c > o and
            cuerpo > 0 and
            (l - min(o,c)) >= 2 * cuerpo and
            (h - max(o,c)) <= cuerpo * 0.3):
            patrones.append({"vela": i, "patron": "MARTILLO", "señal": "alcista", "fuerza": "alta"})

        # Estrella fugaz bajista
        if (c < o and
            cuerpo > 0 and
            (h - max(o,c)) >= 2 * cuerpo and
            (min(o,c) - l) <= cuerpo * 0.3):
            patrones.append({"vela": i, "patron": "ESTRELLA_FUGAZ", "señal": "bajista", "fuerza": "alta"})

        # Envolvente alcista
        if c2 < o2 and c > o and c > o2 and o < c2:
            patrones.append({"vela": i, "patron": "ENVOLVENTE_ALCISTA", "señal": "alcista", "fuerza": "muy_alta"})

        # Envolvente bajista
        if c2 > o2 and c < o and c < o2 and o > c2:
            patrones.append({"vela": i, "patron": "ENVOLVENTE_BAJISTA", "señal": "bajista", "fuerza": "muy_alta"})

        # Marubozu alcista (vela sin sombras, momentum fuerte)
        if (c > o and
            cuerpo / rango > 0.9 if rango > 0 else False and
            vols[i] > vol_prom * 1.3):
            patrones.append({"vela": i, "patron": "MARUBOZU_ALCISTA", "señal": "alcista", "fuerza": "muy_alta"})

        # Marubozu bajista
        if (c < o and
            cuerpo / rango > 0.9 if rango > 0 else False and
            vols[i] > vol_prom * 1.3):
            patrones.append({"vela": i, "patron": "MARUBOZU_BAJISTA", "señal": "bajista", "fuerza": "muy_alta"})

    return patrones[-10:] if len(patrones) > 10 else patrones

def calcular_niveles(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    closes = df["close"].values
    highs  = df["high"].values
    lows   = df["low"].values

    # Soporte y resistencia simples
    resistencia = np.max(highs[-20:])
    soporte     = np.min(lows[-20:])
    precio      = closes[-1]

    # RSI rapido
    deltas = np.diff(closes[-15:])
    ganancias = np.where(deltas > 0, deltas, 0)
    perdidas  = np.where(deltas < 0, -deltas, 0)
    avg_gan = np.mean(ganancias) if np.mean(ganancias) > 0 else 0.0001
    avg_per = np.mean(perdidas)  if np.mean(perdidas)  > 0 else 0.0001
    rsi = 100 - (100 / (1 + avg_gan / avg_per))

    # Tendencia corto plazo
    ma5  = np.mean(closes[-5:])
    ma20 = np.mean(closes[-20:])
    tendencia = "alcista" if ma5 > ma20 else "bajista"

    return {
        "precio": round(precio, 4),
        "soporte": round(soporte, 4),
        "resistencia": round(resistencia, 4),
        "rsi_rapido": round(rsi, 1),
        "tendencia_corto": tendencia,
        "distancia_resistencia_pct": round(((resistencia - precio) / precio) * 100, 2),
        "distancia_soporte_pct": round(((precio - soporte) / precio) * 100, 2),
    }

def analizar_oportunidades() -> dict:
    oportunidades = []
    alertas = []

    for simbolo in ACTIVOS_CRYPTO:
        print(f"[agente_velas] Analizando {simbolo}...")
        df = obtener_velas_binance(simbolo, intervalo="5m", limite=100)
        if df.empty:
            continue

        patrones = detectar_patrones_velas(df)
        niveles  = calcular_niveles(df)

        señales_alcistas = [p for p in patrones if p["señal"] == "alcista"]
        señales_bajistas = [p for p in patrones if p["señal"] == "bajista"]

        if señales_alcistas and niveles.get("rsi_rapido", 50) < 65:
            oportunidades.append({
                "simbolo": simbolo,
                "tipo": "COMPRA",
                "precio": niveles.get("precio"),
                "patrones": [p["patron"] for p in señales_alcistas],
                "rsi": niveles.get("rsi_rapido"),
                "soporte": niveles.get("soporte"),
                "resistencia": niveles.get("resistencia"),
                "distancia_resistencia": niveles.get("distancia_resistencia_pct"),
            })

        if señales_bajistas and niveles.get("rsi_rapido", 50) > 35:
            alertas.append({
                "simbolo": simbolo,
                "tipo": "VENTA/EVITAR",
                "precio": niveles.get("precio"),
                "patrones": [p["patron"] for p in señales_bajistas],
                "rsi": niveles.get("rsi_rapido"),
            })

    # Resumen para Ollama
    resumen_opor = "\n".join([
        f"OPORTUNIDAD {o['simbolo']}: {o['tipo']} | precio={o['precio']} | "
        f"patrones={o['patrones']} | RSI={o['rsi']} | "
        f"dist_resistencia={o['distancia_resistencia']}%"
        for o in oportunidades
    ]) or "Sin oportunidades claras en este ciclo"

    resumen_alertas = "\n".join([
        f"ALERTA {a['simbolo']}: {a['tipo']} | precio={a['precio']} | patrones={a['patrones']}"
        for a in alertas
    ]) or "Sin alertas"

    print("[agente_velas] Generando recomendaciones con Ollama...")
    respuesta = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "system",
                "content": "Eres un trader experto en analisis tecnico de velas japonesas. Analiza las oportunidades detectadas y entrega recomendaciones claras de entrada con: precio de entrada, stop loss sugerido, take profit sugerido, y nivel de confianza. Responde en espanol, de forma concisa y accionable."
            },
            {
                "role": "user",
                "content": f"OPORTUNIDADES:\n{resumen_opor}\n\nALERTAS:\n{resumen_alertas}"
            }
        ]
    )

    return {
        "oportunidades": oportunidades,
        "alertas": alertas,
        "recomendaciones": respuesta["message"]["content"],
        "timestamp": datetime.now().strftime("%H:%M:%S")
    }

def obtener_reporte_velas() -> str:
    resultado = analizar_oportunidades()
    return resultado.get("recomendaciones", "Sin señales de velas")