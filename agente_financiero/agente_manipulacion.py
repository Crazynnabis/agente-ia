# agente_financiero/agente_manipulacion.py
import numpy as np
import pandas as pd
import requests
from datetime import datetime
from agente_financiero.cache_mercado import obtener_velas

ACTIVOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

def detectar_spoofing(simbolo: str) -> dict:
    try:
        # Obtiene libro de ordenes
        r = requests.get(
            "https://api.binance.com/api/v3/depth",
            params={"symbol": simbolo, "limit": 50}, timeout=10
        )
        book  = r.json()
        bids  = [[float(p), float(q)] for p, q in book.get("bids", [])]
        asks  = [[float(p), float(q)] for p, q in book.get("asks", [])]

        if not bids or not asks:
            return {"simbolo": simbolo, "error": "Sin datos"}

        # Detecta ordenes grandes que podrian ser spoofing
        avg_bid_vol = np.mean([b[1] for b in bids])
        avg_ask_vol = np.mean([a[1] for a in asks])

        # Ordenes sospechosas — mas de 5x el promedio
        bids_sospechosos = [(p, q) for p, q in bids if q > avg_bid_vol * 5]
        asks_sospechosos = [(p, q) for p, q in asks if q > avg_ask_vol * 5]

        precio_actual = bids[0][0]

        # Calcula presion real vs aparente
        vol_total_bids = sum(q for _, q in bids)
        vol_total_asks = sum(q for _, q in asks)
        ratio_real     = vol_total_bids / vol_total_asks if vol_total_asks > 0 else 1.0

        # Sin ordenes sospechosas
        vol_bids_limpio = sum(q for _, q in bids if q <= avg_bid_vol * 5)
        vol_asks_limpio = sum(q for _, q in asks if q <= avg_ask_vol * 5)
        ratio_limpio    = vol_bids_limpio / vol_asks_limpio if vol_asks_limpio > 0 else 1.0

        # Diferencia entre ratio real y limpio indica manipulacion
        diferencia = abs(ratio_real - ratio_limpio)

        manipulacion_detectada = False
        tipo_manipulacion      = "NINGUNA"
        alerta                 = ""

        if diferencia > 0.5 and bids_sospechosos:
            manipulacion_detectada = True
            tipo_manipulacion      = "SPOOFING_COMPRA"
            alerta = f"Ordenes grandes de compra sospechosas cerca de ${precio_actual} — posible trampa alcista"
        elif diferencia > 0.5 and asks_sospechosos:
            manipulacion_detectada = True
            tipo_manipulacion      = "SPOOFING_VENTA"
            alerta = f"Ordenes grandes de venta sospechosas cerca de ${precio_actual} — posible trampa bajista"
        elif len(bids_sospechosos) > 3:
            tipo_manipulacion = "PARED_COMPRA_SOSPECHOSA"
            alerta = f"{len(bids_sospechosos)} ordenes grandes de compra — posible manipulacion"
        elif len(asks_sospechosos) > 3:
            tipo_manipulacion = "PARED_VENTA_SOSPECHOSA"
            alerta = f"{len(asks_sospechosos)} ordenes grandes de venta — posible manipulacion"

        return {
            "simbolo":               simbolo,
            "precio":                precio_actual,
            "ratio_libro_real":      round(ratio_real, 3),
            "ratio_libro_limpio":    round(ratio_limpio, 3),
            "diferencia":            round(diferencia, 3),
            "bids_sospechosos":      len(bids_sospechosos),
            "asks_sospechosos":      len(asks_sospechosos),
            "manipulacion_detectada":manipulacion_detectada,
            "tipo_manipulacion":     tipo_manipulacion,
            "alerta":                alerta,
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def detectar_wash_trading(simbolo: str) -> dict:
    try:
        df = obtener_velas(simbolo, "5m", 50)
        if df.empty:
            return {"simbolo": simbolo, "error": "Sin datos"}

        closes  = df["close"].values
        volumes = df["volume"].values

        # Wash trading — volumen alto sin movimiento de precio
        cambios_precio = np.abs(np.diff(closes) / closes[:-1])
        volumen_reciente = volumes[-10:]
        cambio_reciente  = cambios_precio[-10:]

        vol_prom    = np.mean(volumes)
        precio_prom = np.mean(cambios_precio)

        # Detecta velas con volumen muy alto pero precio casi sin moverse
        wash_velas = []
        for i in range(len(volumen_reciente)):
            if volumen_reciente[i] > vol_prom * 2 and cambio_reciente[i] < precio_prom * 0.3:
                wash_velas.append(i)

        wash_detectado = len(wash_velas) >= 2
        wash_score     = round(len(wash_velas) / len(volumen_reciente) * 100, 1)

        return {
            "simbolo":        simbolo,
            "wash_detectado": wash_detectado,
            "wash_score":     wash_score,
            "velas_sospechosas": len(wash_velas),
            "alerta":         f"Posible wash trading — {len(wash_velas)} velas con volumen alto sin movimiento" if wash_detectado else "",
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def analizar_manipulacion_completo() -> list:
    resultados = []
    for simbolo in ACTIVOS:
        print(f"[agente_manipulacion] Analizando {simbolo}...")
        spoofing = detectar_spoofing(simbolo)
        wash     = detectar_wash_trading(simbolo)

        if "error" not in spoofing and "error" not in wash:
            riesgo_total = 0
            alertas      = []

            if spoofing.get("manipulacion_detectada"):
                riesgo_total += 3
                alertas.append(spoofing["alerta"])
            if wash.get("wash_detectado"):
                riesgo_total += 2
                alertas.append(wash["alerta"])
            if spoofing.get("tipo_manipulacion") != "NINGUNA":
                riesgo_total += 1

            nivel_riesgo = "ALTO" if riesgo_total >= 4 else "MEDIO" if riesgo_total >= 2 else "BAJO"
            debe_evitar  = riesgo_total >= 3

            resultados.append({
                "simbolo":      simbolo,
                "spoofing":     spoofing,
                "wash_trading": wash,
                "riesgo_total": riesgo_total,
                "nivel_riesgo": nivel_riesgo,
                "debe_evitar":  debe_evitar,
                "alertas":      alertas,
                "timestamp":    datetime.now().strftime("%H:%M:%S"),
            })

    return resultados

def obtener_reporte_manipulacion() -> str:
    resultados = analizar_manipulacion_completo()
    lineas = []
    for r in resultados:
        if r.get("nivel_riesgo") != "BAJO":
            lineas.append(
                f"{r['simbolo']}: RIESGO {r['nivel_riesgo']} | "
                f"evitar={r['debe_evitar']} | {' | '.join(r['alertas'])}"
            )
    return "\n".join(lineas) if lineas else "Sin manipulacion detectada"