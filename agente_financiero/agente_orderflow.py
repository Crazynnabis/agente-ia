# agente_financiero/agente_orderflow.py
import requests
import numpy as np
from datetime import datetime

ACTIVOS_DEFAULT = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

# Umbrales para detección de imbalance significativo
IMBALANCE_EXTREMO  = 30   # % de desequilibrio extremo
IMBALANCE_ALTO     = 20   # % de desequilibrio alto
PARED_CERCANA_PCT  = 0.3  # % de distancia para considerar pared cercana

def obtener_libro_ordenes(simbolo: str, profundidad: int = 50) -> dict:
    """Usa profundidad 50 para detectar mejor las paredes institucionales."""
    try:
        url  = "https://api.binance.com/api/v3/depth"
        r    = requests.get(url, params={"symbol": simbolo, "limit": profundidad}, timeout=10)
        data = r.json()
        bids = [[float(p), float(q)] for p, q in data.get("bids", [])]
        asks = [[float(p), float(q)] for p, q in data.get("asks", [])]
        if not bids or not asks:
            return {"error": "Sin datos de libro"}
        return {"bids": bids, "asks": asks}
    except Exception as e:
        return {"error": str(e)}

def obtener_trades_recientes(simbolo: str, limite: int = 500) -> list:
    try:
        url = "https://api.binance.com/api/v3/trades"
        r   = requests.get(url, params={"symbol": simbolo, "limit": limite}, timeout=10)
        return r.json()
    except:
        return []

def analizar_niveles_libro(bids: list, asks: list, precio: float) -> dict:
    """
    Analiza el libro por niveles de precio para detectar imbalances específicos.
    Agrupa órdenes en 5 zonas y detecta dónde está la presión real.
    """
    if not bids or not asks:
        return {}

    # Agrupar bids en 5 zonas (0-0.5%, 0.5-1%, 1-1.5%, 1.5-2%, >2%)
    zonas_bid = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    zonas_ask = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}

    for p, q in bids:
        dist = ((precio - p) / precio) * 100
        zona = min(int(dist / 0.5), 4)
        zonas_bid[zona] += q

    for p, q in asks:
        dist = ((p - precio) / precio) * 100
        zona = min(int(dist / 0.5), 4)
        zonas_ask[zona] += q

    # Imbalance por zona cercana (primeras 2 zonas = 0-1%)
    vol_bid_cercano = zonas_bid[0] + zonas_bid[1]
    vol_ask_cercano = zonas_ask[0] + zonas_ask[1]
    total_cercano   = vol_bid_cercano + vol_ask_cercano

    imbalance_cercano = 0
    if total_cercano > 0:
        imbalance_cercano = ((vol_bid_cercano - vol_ask_cercano) / total_cercano) * 100

    # Detectar pared institucional — orden > 3x el promedio
    promedio_bid = np.mean([q for _, q in bids]) if bids else 0
    promedio_ask = np.mean([q for _, q in asks]) if asks else 0

    paredes_compra = [(p, q) for p, q in bids if q > promedio_bid * 3]
    paredes_venta  = [(p, q) for p, q in asks if q > promedio_ask * 3]

    pared_compra_cercana = None
    pared_venta_cercana  = None

    if paredes_compra:
        mejor_pared_c = max(paredes_compra, key=lambda x: x[1])
        dist_c = ((precio - mejor_pared_c[0]) / precio) * 100
        if dist_c < 2.0:
            pared_compra_cercana = {"precio": mejor_pared_c[0], "volumen": mejor_pared_c[1], "distancia_pct": round(dist_c, 3)}

    if paredes_venta:
        mejor_pared_v = max(paredes_venta, key=lambda x: x[1])
        dist_v = ((mejor_pared_v[0] - precio) / precio) * 100
        if dist_v < 2.0:
            pared_venta_cercana = {"precio": mejor_pared_v[0], "volumen": mejor_pared_v[1], "distancia_pct": round(dist_v, 3)}

    return {
        "imbalance_cercano_pct": round(imbalance_cercano, 2),
        "vol_bid_cercano":       round(vol_bid_cercano, 2),
        "vol_ask_cercano":       round(vol_ask_cercano, 2),
        "pared_compra_cercana":  pared_compra_cercana,
        "pared_venta_cercana":   pared_venta_cercana,
        "zonas_bid":             {k: round(v, 2) for k, v in zonas_bid.items()},
        "zonas_ask":             {k: round(v, 2) for k, v in zonas_ask.items()},
    }

def analizar_orderflow(simbolo: str) -> dict:
    libro = obtener_libro_ordenes(simbolo, profundidad=50)
    if "error" in libro:
        return {"simbolo": simbolo, "error": libro["error"]}

    bids = libro["bids"]
    asks = libro["asks"]

    vol_compra    = sum(q for _, q in bids)
    vol_venta     = sum(q for _, q in asks)
    ratio         = vol_compra / vol_venta if vol_venta > 0 else 1.0
    precio_actual = bids[0][0]
    pared_compra  = max(bids, key=lambda x: x[1])
    pared_venta   = max(asks, key=lambda x: x[1])
    imbalance     = (vol_compra - vol_venta) / (vol_compra + vol_venta) * 100

    # Análisis por niveles — detección de imbalance cercano
    niveles = analizar_niveles_libro(bids, asks, precio_actual)
    imbalance_cercano = niveles.get("imbalance_cercano_pct", 0)

    trades          = obtener_trades_recientes(simbolo, 500)
    vol_market_buy  = sum(float(t["qty"]) for t in trades if not t.get("isBuyerMaker", True))
    vol_market_sell = sum(float(t["qty"]) for t in trades if t.get("isBuyerMaker", False))
    delta           = vol_market_buy - vol_market_sell
    total_vol       = vol_market_buy + vol_market_sell
    delta_pct       = (delta / total_vol * 100) if total_vol > 0 else 0

    # ── Señal combinada: libro + trades + imbalance cercano ──
    señal  = "NEUTRAL"
    fuerza = "debil"

    # Imbalance extremo en zona cercana — señal más precisa
    if imbalance_cercano > IMBALANCE_EXTREMO and delta > 0:
        señal  = "PRESION_COMPRADORA_FUERTE"
        fuerza = "extrema"
    elif imbalance_cercano < -IMBALANCE_EXTREMO and delta < 0:
        señal  = "PRESION_VENDEDORA_FUERTE"
        fuerza = "extrema"
    elif ratio > 1.5 and delta > 0:
        señal  = "PRESION_COMPRADORA_FUERTE"
        fuerza = "alta"
    elif ratio > 1.2 and delta > 0:
        señal  = "PRESION_COMPRADORA"
        fuerza = "media"
    elif ratio < 0.67 and delta < 0:
        señal  = "PRESION_VENDEDORA_FUERTE"
        fuerza = "alta"
    elif ratio < 0.8 and delta < 0:
        señal  = "PRESION_VENDEDORA"
        fuerza = "media"
    elif abs(imbalance_cercano) > IMBALANCE_ALTO:
        señal  = "IMBALANCE_" + ("ALCISTA" if imbalance_cercano > 0 else "BAJISTA")
        fuerza = "media"
    elif abs(imbalance) > IMBALANCE_ALTO:
        señal  = "IMBALANCE_" + ("ALCISTA" if imbalance > 0 else "BAJISTA")
        fuerza = "media"

    distancia_pared_venta  = ((pared_venta[0]  - precio_actual) / precio_actual) * 100
    distancia_pared_compra = ((precio_actual - pared_compra[0]) / precio_actual) * 100

    pared_alerta = None
    if distancia_pared_venta < PARED_CERCANA_PCT:
        pared_alerta = f"RESISTENCIA_FUERTE en {pared_venta[0]} ({pared_venta[1]:.2f} unidades)"
    if distancia_pared_compra < PARED_CERCANA_PCT:
        pared_alerta = f"SOPORTE_FUERTE en {pared_compra[0]} ({pared_compra[1]:.2f} unidades)"

    # Alerta si hay pared institucional muy cercana
    pared_inst_compra = niveles.get("pared_compra_cercana")
    pared_inst_venta  = niveles.get("pared_venta_cercana")
    if pared_inst_venta and pared_inst_venta["distancia_pct"] < 0.5:
        pared_alerta = f"PARED_INSTITUCIONAL_VENTA en {pared_inst_venta['precio']} ({pared_inst_venta['distancia_pct']}%)"
    if pared_inst_compra and pared_inst_compra["distancia_pct"] < 0.5:
        pared_alerta = f"PARED_INSTITUCIONAL_COMPRA en {pared_inst_compra['precio']} ({pared_inst_compra['distancia_pct']}%)"

    return {
        "simbolo":               simbolo,
        "precio":                precio_actual,
        "ratio_compra_venta":    round(ratio, 3),
        "vol_compra":            round(vol_compra, 2),
        "vol_venta":             round(vol_venta, 2),
        "imbalance_pct":         round(imbalance, 2),
        "imbalance_cercano_pct": round(imbalance_cercano, 2),
        "delta_trades":          round(delta, 2),
        "delta_pct":             round(delta_pct, 2),
        "señal":                 señal,
        "fuerza":                fuerza,
        "pared_compra":          pared_compra,
        "pared_venta":           pared_venta,
        "pared_inst_compra":     pared_inst_compra,
        "pared_inst_venta":      pared_inst_venta,
        "dist_pared_venta_pct":  round(distancia_pared_venta, 3),
        "dist_pared_compra_pct": round(distancia_pared_compra, 3),
        "pared_alerta":          pared_alerta,
        "niveles":               niveles,
        "timestamp":             datetime.now().strftime("%H:%M:%S"),
    }

def analizar_todos_activos(activos: list = None) -> list:
    if activos is None:
        activos = ACTIVOS_DEFAULT
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
                f"imbalance_cercano={r['imbalance_cercano_pct']}% | "
                f"pared={r.get('pared_alerta','ninguna')}"
            )
    return "\n".join(lineas)
