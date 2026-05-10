# agente_financiero/agente_liquidaciones.py
import requests
import numpy as np
from datetime import datetime

ACTIVOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

def obtener_long_short_ratio(simbolo: str) -> dict:
    try:
        url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
        r = requests.get(url, params={
            "symbol": simbolo, "period": "5m", "limit": 12
        }, timeout=10)
        data = r.json()

        if not isinstance(data, list) or len(data) == 0:
            return {"error": "Sin datos"}

        ratio_actual  = float(data[-1].get("longShortRatio", 1.0))
        ratio_inicial = float(data[0].get("longShortRatio", 1.0))
        longs_pct     = float(data[-1].get("longAccount", 0.5)) * 100
        shorts_pct    = float(data[-1].get("shortAccount", 0.5)) * 100
        tendencia     = "longs_aumentando" if ratio_actual > ratio_inicial else "shorts_aumentando"

        if longs_pct > 65:
            señal  = "EXCESO_LONGS — mercado sobrecalentado alcista, posible caida"
            accion = "VENDER"
            fuerza = "alta"
        elif longs_pct < 35:
            señal  = "EXCESO_SHORTS — mercado pesimista extremo, posible rebote"
            accion = "COMPRAR"
            fuerza = "alta"
        elif longs_pct > 55:
            señal  = "LONGS_DOMINANDO — sesgo alcista moderado"
            accion = "COMPRAR"
            fuerza = "media"
        elif shorts_pct > 55:
            señal  = "SHORTS_DOMINANDO — sesgo bajista moderado"
            accion = "VENDER"
            fuerza = "media"
        else:
            señal  = "EQUILIBRADO — sin sesgo claro"
            accion = "ESPERAR"
            fuerza = "baja"

        return {
            "simbolo":      simbolo,
            "ratio":        round(ratio_actual, 3),
            "longs_pct":    round(longs_pct, 2),
            "shorts_pct":   round(shorts_pct, 2),
            "tendencia":    tendencia,
            "señal":        señal,
            "accion":       accion,
            "fuerza":       fuerza,
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def obtener_taker_ratio(simbolo: str) -> dict:
    try:
        url = "https://fapi.binance.com/futures/data/takerlongshortRatio"
        r = requests.get(url, params={
            "symbol": simbolo, "period": "5m", "limit": 12
        }, timeout=10)
        data = r.json()

        if not isinstance(data, list) or len(data) == 0:
            return {"error": "Sin datos"}

        ratio_actual = float(data[-1].get("buySellRatio", 1.0))
        buy_vol      = float(data[-1].get("buyVol", 0))
        sell_vol     = float(data[-1].get("sellVol", 0))

        historial    = [float(d.get("buySellRatio", 1.0)) for d in data]
        promedio     = np.mean(historial)
        desviacion   = (ratio_actual - promedio) / promedio * 100 if promedio > 0 else 0

        if ratio_actual > 1.5:
            señal_taker = "COMPRADORES_AGRESIVOS — momentum alcista fuerte"
        elif ratio_actual > 1.1:
            señal_taker = "SESGO_COMPRA — compradores activos"
        elif ratio_actual < 0.67:
            señal_taker = "VENDEDORES_AGRESIVOS — momentum bajista fuerte"
        elif ratio_actual < 0.9:
            señal_taker = "SESGO_VENTA — vendedores activos"
        else:
            señal_taker = "EQUILIBRADO"

        return {
            "simbolo":       simbolo,
            "taker_ratio":   round(ratio_actual, 3),
            "buy_vol":       round(buy_vol, 2),
            "sell_vol":      round(sell_vol, 2),
            "vs_promedio":   round(desviacion, 2),
            "señal":         señal_taker,
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def obtener_mapa_liquidaciones(simbolo: str) -> dict:
    try:
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/premiumIndex",
            params={"symbol": simbolo}, timeout=10
        )
        precio_actual = float(r.json().get("markPrice", 0))

        r2 = requests.get(
            "https://fapi.binance.com/fapi/v1/depth",
            params={"symbol": simbolo, "limit": 50}, timeout=10
        )
        book  = r2.json()
        bids  = [[float(p), float(q)] for p, q in book.get("bids", [])]
        asks  = [[float(p), float(q)] for p, q in book.get("asks", [])]

        if not bids or not asks:
            return {"simbolo": simbolo, "precio_actual": precio_actual}

        avg_bid = np.mean([b[1] for b in bids])
        avg_ask = np.mean([a[1] for a in asks])

        bids_grandes = [(p, q) for p, q in bids if q > avg_bid * 3]
        asks_grandes = [(p, q) for p, q in asks if q > avg_ask * 3]

        soporte     = bids_grandes[0][0] if bids_grandes else bids[-1][0]
        resistencia = asks_grandes[0][0] if asks_grandes else asks[-1][0]

        dist_s = round(((precio_actual - soporte) / precio_actual) * 100, 3)
        dist_r = round(((resistencia - precio_actual) / precio_actual) * 100, 3)

        zona_liq_longs  = round(precio_actual * 0.93, 2)
        zona_liq_shorts = round(precio_actual * 1.07, 2)

        if dist_s < 0.3:
            contexto = "EN_SOPORTE_FUERTE — rebote probable"
        elif dist_r < 0.3:
            contexto = "EN_RESISTENCIA_FUERTE — rechazo probable"
        elif len(bids_grandes) > len(asks_grandes):
            contexto = "MAS_SOPORTE_QUE_RESISTENCIA — sesgo alcista"
        else:
            contexto = "EQUILIBRADO"

        return {
            "simbolo":          simbolo,
            "precio_actual":    round(precio_actual, 4),
            "soporte":          round(soporte, 4),
            "resistencia":      round(resistencia, 4),
            "dist_soporte_pct": dist_s,
            "dist_resist_pct":  dist_r,
            "zona_liq_longs":   zona_liq_longs,
            "zona_liq_shorts":  zona_liq_shorts,
            "contexto":         contexto,
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def analizar_liquidaciones_completo() -> list:
    resultados = []
    for simbolo in ACTIVOS:
        print(f"[agente_liquidaciones] Analizando {simbolo}...")
        ls    = obtener_long_short_ratio(simbolo)
        taker = obtener_taker_ratio(simbolo)
        mapa  = obtener_mapa_liquidaciones(simbolo)

        if "error" not in ls and "error" not in mapa:
            votos_compra = sum([
                ls.get("accion") == "COMPRAR",
                "COMPRADORES" in taker.get("señal","") or "COMPRA" in taker.get("señal",""),
                "SOPORTE" in mapa.get("contexto",""),
            ])
            votos_venta = sum([
                ls.get("accion") == "VENDER",
                "VENDEDORES" in taker.get("señal","") or "VENTA" in taker.get("señal",""),
                "RESISTENCIA" in mapa.get("contexto",""),
            ])

            señal_final = "COMPRAR" if votos_compra >= 2 else ("VENDER" if votos_venta >= 2 else "ESPERAR")

            resultados.append({
                "simbolo":       simbolo,
                "long_short":    ls,
                "taker":         taker,
                "mapa":          mapa,
                "votos_compra":  votos_compra,
                "votos_venta":   votos_venta,
                "señal_final":   señal_final,
            })
        else:
            resultados.append({"simbolo": simbolo, "error": "Sin datos"})

    return resultados

def obtener_reporte_liquidaciones() -> str:
    resultados = analizar_liquidaciones_completo()
    lineas = []
    for r in resultados:
        if "error" not in r:
            lineas.append(
                f"{r['simbolo']}: {r['señal_final']} | "
                f"longs={r['long_short'].get('longs_pct','N/A')}% | "
                f"taker={r['taker'].get('señal','N/A')} | "
                f"contexto={r['mapa'].get('contexto','N/A')}"
            )
    return "\n".join(lineas)