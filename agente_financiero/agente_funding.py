# agente_financiero/agente_funding.py
import requests
import numpy as np
from datetime import datetime

ACTIVOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

def obtener_funding_rate(simbolo: str) -> dict:
    try:
        # Funding rate actual
        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        r = requests.get(url, params={"symbol": simbolo}, timeout=10)
        data = r.json()
        funding_rate = float(data.get("lastFundingRate", 0))
        mark_price   = float(data.get("markPrice", 0))
        index_price  = float(data.get("indexPrice", 0))
        
        # Historial de funding rates
        url2 = "https://fapi.binance.com/fapi/v1/fundingRate"
        r2 = requests.get(url2, params={"symbol": simbolo, "limit": 8}, timeout=10)
        historial = r2.json()
        rates_hist = [float(h["fundingRate"]) for h in historial]
        
        promedio_8 = np.mean(rates_hist)
        tendencia  = "subiendo" if rates_hist[-1] > rates_hist[0] else "bajando"
        
        # Interpretacion
        if funding_rate < -0.001:
            señal = "MUY_ALCISTA — shorts pagando mucho, reversión inminente"
            accion = "COMPRAR"
            fuerza = "alta"
        elif funding_rate < -0.0003:
            señal = "ALCISTA — funding negativo, presión de shorts"
            accion = "COMPRAR"
            fuerza = "media"
        elif funding_rate > 0.001:
            señal = "MUY_BAJISTA — longs pagando mucho, posible caida"
            accion = "VENDER"
            fuerza = "alta"
        elif funding_rate > 0.0003:
            señal = "BAJISTA — funding positivo alto, longs sobrecalentados"
            accion = "VENDER"
            fuerza = "media"
        else:
            señal = "NEUTRAL — funding equilibrado"
            accion = "ESPERAR"
            fuerza = "baja"
        
        return {
            "simbolo":        simbolo,
            "funding_rate":   round(funding_rate * 100, 4),
            "funding_8h_pct": round(funding_rate * 100 * 3 * 365, 2),
            "promedio_8_periodos": round(promedio_8 * 100, 4),
            "mark_price":     round(mark_price, 2),
            "index_price":    round(index_price, 2),
            "diferencia_pct": round(((mark_price - index_price) / index_price) * 100, 4),
            "tendencia":      tendencia,
            "señal":          señal,
            "accion":         accion,
            "fuerza":         fuerza,
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def obtener_open_interest(simbolo: str) -> dict:
    try:
        url = "https://fapi.binance.com/fapi/v1/openInterest"
        r = requests.get(url, params={"symbol": simbolo}, timeout=10)
        data = r.json()
        oi = float(data.get("openInterest", 0))
        
        # Historial OI
        url2 = "https://fapi.binance.com/futures/data/openInterestHist"
        r2 = requests.get(url2, params={
            "symbol": simbolo, "period": "5m", "limit": 12
        }, timeout=10)
        hist = r2.json()
        
        if isinstance(hist, list) and len(hist) > 2:
            oi_inicial = float(hist[0].get("sumOpenInterest", oi))
            oi_actual  = float(hist[-1].get("sumOpenInterest", oi))
            cambio_oi  = ((oi_actual - oi_inicial) / oi_inicial) * 100 if oi_inicial > 0 else 0
            
            if cambio_oi > 2:
                oi_señal = "CRECIENDO_FUERTE — nuevas posiciones abriendo"
            elif cambio_oi > 0.5:
                oi_señal = "CRECIENDO — interes en aumento"
            elif cambio_oi < -2:
                oi_señal = "CAYENDO_FUERTE — liquidaciones o cierres masivos"
            else:
                oi_señal = "ESTABLE"
        else:
            cambio_oi = 0
            oi_señal  = "Sin historial"
        
        return {
            "simbolo":    simbolo,
            "oi_actual":  round(oi, 2),
            "cambio_pct": round(cambio_oi, 3),
            "señal":      oi_señal,
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def analizar_funding_completo() -> list:
    resultados = []
    for simbolo in ACTIVOS:
        print(f"[agente_funding] Analizando {simbolo}...")
        fr  = obtener_funding_rate(simbolo)
        oi  = obtener_open_interest(simbolo)
        
        if "error" not in fr and "error" not in oi:
            # Confluencia funding + OI
            if fr["accion"] == "COMPRAR" and "CRECIENDO" in oi.get("señal",""):
                confluencia = "ALCISTA_CONFIRMADA — funding negativo + OI creciendo"
            elif fr["accion"] == "VENDER" and "CRECIENDO" in oi.get("señal",""):
                confluencia = "BAJISTA_CONFIRMADA — funding positivo + OI creciendo"
            elif fr["accion"] == "COMPRAR" and "CAYENDO" in oi.get("señal",""):
                confluencia = "POSIBLE_ALCISTA — funding negativo + OI cayendo (short squeeze)"
            else:
                confluencia = f"MIXTA — {fr['señal']}"
            
            resultados.append({
                "simbolo":     simbolo,
                "funding":     fr,
                "open_interest": oi,
                "confluencia": confluencia,
                "accion":      fr["accion"],
                "fuerza":      fr["fuerza"],
            })
        else:
            resultados.append({"simbolo": simbolo, "error": "Sin datos"})
    
    return resultados

def obtener_reporte_funding() -> str:
    resultados = analizar_funding_completo()
    lineas = []
    for r in resultados:
        if "error" not in r:
            lineas.append(
                f"{r['simbolo']}: {r['accion']} ({r['fuerza']}) | "
                f"funding={r['funding']['funding_rate']}% | "
                f"APY={r['funding']['funding_8h_pct']}% | "
                f"OI={r['open_interest']['señal']} | "
                f"confluencia={r['confluencia']}"
            )
    return "\n".join(lineas)