# agente_financiero/agente_orderflow.py
import requests
import numpy as np
from datetime import datetime

def obtener_libro_ordenes(simbolo: str, profundidad: int = 20) -> dict:
    try:
        url = "https://api.binance.com/api/v3/depth"
        r = requests.get(url, params={"symbol": simbolo, "limit": profundidad}, timeout=10)
        data = r.json()
        bids = [[float(p), float(q)] for p, q in data["bids"]]
        asks = [[float(p), float(q)] for p, q in data["asks"]]
        return {"bids": bids, "asks": asks}
    except Exception as e:
        return {"error": str(e)}

def obtener_trades_recientes(simbolo: str, limite: int = 500) -> list:
    try:
        url = "https://api.binance.com/api/v3/trades"
        r = requests.get(url, params={"symbol": simbolo, "limit": limite}, timeout=10)
        return r.json()
    except:
        return []

def analizar_orderflow(simbolo: str) -> dict:
    libro = obtener_libro_ordenes(simbolo, profundidad=20)
    if "error" in libro:
        return {"simbolo": simbolo, "error": libro["error"]}

    bids = libro["bids"]
    asks = libro["asks"]

    # Volumen total en cada lado
    vol_compra = sum(q for _, q in bids)
    vol_venta  = sum(q for _, q in asks)
    ratio      = vol_compra / vol_venta if vol_venta > 0 else 1.0

    # Paredes — órdenes grandes que bloquean el precio
    precio_actual = bids[0][0]
    pared_compra = max(bids, key=lambda x: x[1])
    pared_venta  = max(asks, key=lambda x: x[1])

    # Imbalance — desequilibrio entre compra y venta
    imbalance = (vol_compra - vol_venta) / (vol_compra + vol_venta) * 100

    # Delta de trades recientes
    trades = obtener_trades_recientes(simbolo, 500)
    vol_market_buy  = sum(float(t["qty"]) for t in trades if not t["isBuyerMaker"])
    vol_market_sell = sum(float(t["qty"]) for t in trades if t["isBuyerMaker"])
    delta = vol_market_buy - vol_market_sell
    delta_pct = (delta / (vol_market_buy + vol_market_sell) * 100) if (vol_market_buy + vol_market_sell) > 0 else 0

    # Señal de orderflow
    señal = "NEUTRAL"
    fuerza = "debil"

    if ratio > 1.5 and delta > 0:
        señal = "PRESION_COMPRADORA_FUERTE"
        fuerza = "alta"
    elif ratio > 1.2 and delta > 0:
        señal = "PRESION_COMPRADORA"
        fuerza = "media"
    elif ratio < 0.67 and delta < 0:
        señal = "PRESION_VENDEDORA_FUERTE"
        fuerza = "alta"
    elif ratio < 0.8 and delta < 0:
        señal = "PRESION_VENDEDORA"
        fuerza = "media"
    elif abs(imbalance) > 20:
        señal = "IMBALANCE_" + ("ALCISTA" if imbalance > 0 else "BAJISTA")
        fuerza = "media"

    # Detecta si hay pared que bloquea subida o bajada
    distancia_pared_venta  = ((pared_venta[0]  - precio_actual) / precio_actual) * 100
    distancia_pared_compra = ((precio_actual - pared_compra[0]) / precio_actual) * 100

    pared_alerta = None
    if distancia_pared_venta < 0.3:
        pared_alerta = f"RESISTENCIA_FUERTE en {pared_venta[0]} ({pared_venta[1]:.2f} unidades)"
    if distancia_pared_compra < 0.3:
        pared_alerta = f"SOPORTE_FUERTE en {pared_compra[0]} ({pared_compra[1]:.2f} unidades)"

    return {
        "simbolo":              simbolo,
        "precio":               precio_actual,
        "ratio_compra_venta":   round(ratio, 3),
        "vol_compra":           round(vol_compra, 2),
        "vol_venta":            round(vol_venta, 2),
        "imbalance_pct":        round(imbalance, 2),
        "delta_trades":         round(delta, 2),
        "delta_pct":            round(delta_pct, 2),
        "señal":                señal,
        "fuerza":               fuerza,
        "pared_compra":         pared_compra,
        "pared_venta":          pared_venta,
        "dist_pared_venta_pct": round(distancia_pared_venta, 3),
        "dist_pared_compra_pct":round(distancia_pared_compra, 3),
        "pared_alerta":         pared_alerta,
        "timestamp":            datetime.now().strftime("%H:%M:%S"),
    }

def analizar_todos_activos(activos: list = None) -> list:
    if activos is None:
        activos = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
    resultados = []
    for simbolo in activos:
        print(f"[agente_orderflow] Analizando {simbolo}...")
        r = analizar_orderflow(simbolo)
        resultados.append(r)
    return resultados

def obtener_reporte_orderflow() -> str:
    resultados = analizar_todos_activos()
    lineas = []
    for r in resultados:
        if "error" not in r:
            lineas.append(
                f"{r['simbolo']}: {r['señal']} ({r['fuerza']}) | "
                f"ratio={r['ratio_compra_venta']} | "
                f"delta={r['delta_pct']}% | "
                f"imbalance={r['imbalance_pct']}% | "
                f"pared={r.get('pared_alerta','ninguna')}"
            )
    return "\n".join(lineas)