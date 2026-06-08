# agente_financiero/agente_funding.py
import requests
import numpy as np
from datetime import datetime

ACTIVOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

# Umbrales de funding extremo — señales de alta probabilidad
FUNDING_EXTREMO_POSITIVO = 0.001   # >0.1% por ciclo — longs sobreextendidos
FUNDING_EXTREMO_NEGATIVO = -0.001  # <-0.1% por ciclo — shorts sobreextendidos
FUNDING_ALTO_POSITIVO    = 0.0003
FUNDING_ALTO_NEGATIVO    = -0.0003

def obtener_funding_rate(simbolo: str) -> dict:
    try:
        url  = "https://fapi.binance.com/fapi/v1/premiumIndex"
        r    = requests.get(url, params={"symbol": simbolo}, timeout=10)
        data = r.json()

        funding_rate = float(data.get("lastFundingRate", 0))
        mark_price   = float(data.get("markPrice", 0))
        index_price  = float(data.get("indexPrice", 0))

        url2 = "https://fapi.binance.com/fapi/v1/fundingRate"
        r2   = requests.get(url2, params={"symbol": simbolo, "limit": 8}, timeout=10)
        historial  = r2.json()
        rates_hist = [float(h["fundingRate"]) for h in historial] if isinstance(historial, list) else [funding_rate]

        promedio_8  = np.mean(rates_hist)
        tendencia   = "subiendo" if rates_hist[-1] > rates_hist[0] else "bajando"
        apy_anual   = funding_rate * 3 * 365 * 100  # 3 pagos/día × 365 días

        # ── Clasificación de señal ────────────────────────────
        if funding_rate <= FUNDING_EXTREMO_NEGATIVO:
            señal   = "EXTREMO_ALCISTA — shorts pagando >0.1%/ciclo, reversión inminente"
            accion  = "COMPRAR"
            fuerza  = "extrema"
            alerta  = True
        elif funding_rate <= FUNDING_ALTO_NEGATIVO:
            señal   = "ALCISTA — funding negativo, presión de shorts"
            accion  = "COMPRAR"
            fuerza  = "alta"
            alerta  = False
        elif funding_rate >= FUNDING_EXTREMO_POSITIVO:
            señal   = "EXTREMO_BAJISTA — longs pagando >0.1%/ciclo, caída inminente"
            accion  = "VENDER"
            fuerza  = "extrema"
            alerta  = True
        elif funding_rate >= FUNDING_ALTO_POSITIVO:
            señal   = "BAJISTA — funding positivo alto, longs sobrecalentados"
            accion  = "VENDER"
            fuerza  = "alta"
            alerta  = False
        else:
            señal   = "NEUTRAL — funding equilibrado"
            accion  = "ESPERAR"
            fuerza  = "baja"
            alerta  = False

        # Alerta Telegram si funding extremo
        if alerta:
            try:
                from agente_financiero.alertas_telegram import enviar_mensaje
                emoji = "🔥" if accion == "COMPRAR" else "❄️"
                enviar_mensaje(
                    f"{emoji} <b>FUNDING EXTREMO — {simbolo}</b>\n"
                    f"──────────────────\n"
                    f"Funding rate: {round(funding_rate*100, 4)}%/ciclo\n"
                    f"APY equivalente: {round(apy_anual, 1)}%\n"
                    f"Señal: {señal}\n"
                    f"Esta condición precede reversiones de precio\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
                print(f"[agente_funding] ⚡ ALERTA FUNDING EXTREMO {simbolo}: {round(funding_rate*100,4)}%")
            except:
                pass

        return {
            "simbolo":             simbolo,
            "funding_rate":        round(funding_rate * 100, 4),
            "funding_apy_anual":   round(apy_anual, 1),
            "promedio_8_periodos": round(promedio_8 * 100, 4),
            "mark_price":          round(mark_price, 2),
            "index_price":         round(index_price, 2),
            "diferencia_pct":      round(((mark_price - index_price) / index_price) * 100, 4) if index_price > 0 else 0,
            "tendencia":           tendencia,
            "señal":               señal,
            "accion":              accion,
            "fuerza":              fuerza,
            "es_extremo":          alerta,
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def obtener_open_interest(simbolo: str) -> dict:
    try:
        url  = "https://fapi.binance.com/fapi/v1/openInterest"
        r    = requests.get(url, params={"symbol": simbolo}, timeout=10)
        data = r.json()
        oi   = float(data.get("openInterest", 0))

        url2 = "https://fapi.binance.com/futures/data/openInterestHist"
        r2   = requests.get(url2, params={"symbol": simbolo, "period": "5m", "limit": 12}, timeout=10)
        hist = r2.json()

        if isinstance(hist, list) and len(hist) > 2:
            oi_inicial = float(hist[0].get("sumOpenInterest", oi))
            oi_actual  = float(hist[-1].get("sumOpenInterest", oi))
            cambio_oi  = ((oi_actual - oi_inicial) / oi_inicial) * 100 if oi_inicial > 0 else 0

            if cambio_oi > 2:
                oi_señal = "CRECIENDO_FUERTE — nuevas posiciones abriendo"
            elif cambio_oi > 0.5:
                oi_señal = "CRECIENDO — interés en aumento"
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
        fr = obtener_funding_rate(simbolo)
        oi = obtener_open_interest(simbolo)

        if "error" not in fr and "error" not in oi:
            # Confluencia funding + OI
            if fr["accion"] == "COMPRAR" and "CRECIENDO" in oi.get("señal",""):
                confluencia = "ALCISTA_CONFIRMADA — funding negativo + OI creciendo"
            elif fr["accion"] == "VENDER" and "CRECIENDO" in oi.get("señal",""):
                confluencia = "BAJISTA_CONFIRMADA — funding positivo + OI creciendo"
            elif fr["accion"] == "COMPRAR" and "CAYENDO" in oi.get("señal",""):
                confluencia = "POSIBLE_ALCISTA — funding negativo + OI cayendo (short squeeze)"
            elif fr.get("es_extremo") and fr["accion"] == "VENDER" and "CAYENDO" in oi.get("señal",""):
                confluencia = "CRASH_INMINENTE — funding extremo + liquidaciones masivas"
            else:
                confluencia = f"MIXTA — {fr['señal']}"

            resultados.append({
                "simbolo":       simbolo,
                "funding":       fr,
                "open_interest": oi,
                "confluencia":   confluencia,
                "accion":        fr["accion"],
                "fuerza":        fr["fuerza"],
                "es_extremo":    fr.get("es_extremo", False),
                "timestamp":     datetime.now().strftime("%H:%M:%S"),
            })
        else:
            resultados.append({"simbolo": simbolo, "error": "Sin datos"})

    return resultados

def obtener_reporte_funding() -> str:
    resultados = analizar_funding_completo()
    lineas = []
    for r in resultados:
        if "error" not in r:
            extremo = "⚡ EXTREMO" if r.get("es_extremo") else ""
            lineas.append(
                f"{r['simbolo']}: {r['accion']} ({r['fuerza']}) {extremo} | "
                f"funding={r['funding']['funding_rate']}% | "
                f"APY={r['funding']['funding_apy_anual']}% | "
                f"OI={r['open_interest']['señal']} | "
                f"confluencia={r['confluencia']}"
            )
    return "\n".join(lineas)
