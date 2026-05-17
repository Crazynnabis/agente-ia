# agente_financiero/agente_mean_reversion.py
import numpy as np
import pandas as pd
from datetime import datetime
from agente_financiero.cache_mercado import obtener_velas

ACTIVOS_CRYPTO   = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
ACTIVOS_ACCIONES = ["AAPL", "NVDA", "MSFT", "TSLA", "SPY", "QQQ"]

def calcular_rsi(closes: np.ndarray, periodo: int = 14) -> float:
    deltas   = np.diff(closes[-periodo*2:])
    ganancias = np.where(deltas > 0, deltas, 0)
    perdidas  = np.where(deltas < 0, -deltas, 0)
    avg_gan  = np.mean(ganancias[-periodo:])
    avg_per  = np.mean(perdidas[-periodo:])
    if avg_per == 0:
        return 100.0
    rs  = avg_gan / avg_per
    return round(100 - (100 / (1 + rs)), 2)

def calcular_zscore(series: np.ndarray, ventana: int = 20) -> float:
    if len(series) < ventana:
        return 0.0
    reciente = series[-ventana:]
    media    = np.mean(reciente)
    std      = np.std(reciente)
    if std == 0:
        return 0.0
    return round((series[-1] - media) / std, 3)

def calcular_bollinger(closes: np.ndarray, periodo: int = 20, desv: float = 2.0) -> dict:
    if len(closes) < periodo:
        return {}
    media  = np.mean(closes[-periodo:])
    std    = np.std(closes[-periodo:])
    return {
        "media":     round(float(media), 4),
        "banda_sup": round(float(media + desv * std), 4),
        "banda_inf": round(float(media - desv * std), 4),
        "ancho":     round(float(4 * std / media * 100), 3),
    }

def analizar_mean_reversion(simbolo: str, intervalo: str = "1h") -> dict:
    try:
        df = obtener_velas(simbolo, intervalo, 100)
        if df.empty or len(df) < 30:
            return {"simbolo": simbolo, "error": "Sin datos"}

        closes = df["close"].values
        highs  = df["high"].values
        lows   = df["low"].values
        precio = float(closes[-1])

        # Indicadores de reversión
        rsi      = calcular_rsi(closes)
        zscore   = calcular_zscore(closes)
        bollinger = calcular_bollinger(closes)

        # ATR para stops
        atr = float(np.mean([highs[i] - lows[i] for i in range(-14, 0)]))

        # Caida/subida reciente
        cambio_1h  = round(((closes[-1] - closes[-2])   / closes[-2])   * 100, 3)
        cambio_4h  = round(((closes[-1] - closes[-5])   / closes[-5])   * 100, 3)
        cambio_24h = round(((closes[-1] - closes[-25])  / closes[-25])  * 100, 3) if len(closes) > 25 else 0

        # Logica de mean reversion
        señal  = "ESPERAR"
        fuerza = "baja"
        razon  = ""
        puntos = 0

        # Condiciones de sobreventa extrema
        if rsi < 25:
            puntos += 3
            razon += f"RSI={rsi} sobreventa extrema. "
        elif rsi < 35:
            puntos += 2
            razon += f"RSI={rsi} sobreventa. "

        if zscore < -2.0:
            puntos += 3
            razon += f"Z-Score={zscore} desviacion extrema. "
        elif zscore < -1.5:
            puntos += 2
            razon += f"Z-Score={zscore} desviacion alta. "

        if bollinger and precio < bollinger["banda_inf"]:
            puntos += 2
            razon += f"Bajo banda inferior Bollinger. "

        if cambio_24h < -5:
            puntos += 2
            razon += f"Caida 24h={cambio_24h}% excesiva. "
        elif cambio_24h < -3:
            puntos += 1
            razon += f"Caida 24h={cambio_24h}%. "

        # Condiciones de sobrecompra extrema
        puntos_venta = 0
        razon_venta  = ""

        if rsi > 75:
            puntos_venta += 3
            razon_venta += f"RSI={rsi} sobrecompra extrema. "
        elif rsi > 65:
            puntos_venta += 2
            razon_venta += f"RSI={rsi} sobrecompra. "

        if zscore > 2.0:
            puntos_venta += 3
            razon_venta += f"Z-Score={zscore} desviacion extrema arriba. "
        elif zscore > 1.5:
            puntos_venta += 2
            razon_venta += f"Z-Score={zscore} desviacion alta arriba. "

        if bollinger and precio > bollinger["banda_sup"]:
            puntos_venta += 2
            razon_venta += f"Sobre banda superior Bollinger. "

        if cambio_24h > 5:
            puntos_venta += 2
            razon_venta += f"Subida 24h={cambio_24h}% excesiva. "

        # Decision final
        if puntos >= 5:
            señal  = "COMPRAR"
            fuerza = "muy_alta"
        elif puntos >= 3:
            señal  = "COMPRAR"
            fuerza = "alta"
        elif puntos_venta >= 5:
            señal  = "VENDER"
            fuerza = "muy_alta"
            razon  = razon_venta
        elif puntos_venta >= 3:
            señal  = "VENDER"
            fuerza = "alta"
            razon  = razon_venta

        # Stop loss y take profit
        media = bollinger.get("media", precio) if bollinger else precio
        if señal == "COMPRAR":
            sl  = round(precio - atr * 2.5, 4)
            tp1 = round(media, 4)
            tp2 = round(bollinger.get("banda_sup", precio + atr * 4) if bollinger else precio + atr * 4, 4)
        elif señal == "VENDER":
            sl  = round(precio + atr * 2.5, 4)
            tp1 = round(media, 4)
            tp2 = round(bollinger.get("banda_inf", precio - atr * 4) if bollinger else precio - atr * 4, 4)
        else:
            sl = tp1 = tp2 = 0

        return {
            "simbolo":     simbolo,
            "precio":      round(precio, 4),
            "rsi":         rsi,
            "zscore":      zscore,
            "bollinger":   bollinger,
            "cambio_1h":   cambio_1h,
            "cambio_4h":   cambio_4h,
            "cambio_24h":  cambio_24h,
            "señal":       señal,
            "fuerza":      fuerza,
            "puntos":      puntos if señal == "COMPRAR" else puntos_venta,
            "razon":       razon.strip(),
            "stop_loss":   sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "atr":         round(atr, 4),
            "timestamp":   datetime.now().strftime("%H:%M:%S"),
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def ejecutar_mean_reversion() -> list:
    resultados = []
    print("[agente_mean] Analizando crypto...")
    for simbolo in ACTIVOS_CRYPTO:
        r = analizar_mean_reversion(simbolo, "1h")
        if "error" not in r:
            resultados.append(r)

    print("[agente_mean] Analizando acciones...")
    for simbolo in ACTIVOS_ACCIONES:
        r = analizar_mean_reversion(simbolo, "1h")
        if "error" not in r:
            resultados.append(r)

    return resultados

def obtener_reporte_mean_reversion() -> str:
    resultados = ejecutar_mean_reversion()
    lineas = []
    for r in resultados:
        if r.get("señal") != "ESPERAR":
            lineas.append(
                f"{r['simbolo']}: {r['señal']} ({r['fuerza']}) | "
                f"RSI={r['rsi']} Z={r['zscore']} | "
                f"24h={r['cambio_24h']}% | puntos={r['puntos']}"
            )
    return "\n".join(lineas) if lineas else "Sin señales Mean Reversion"