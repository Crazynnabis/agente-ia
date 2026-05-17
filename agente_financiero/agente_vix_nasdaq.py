# agente_financiero/agente_vix_nasdaq.py
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import requests
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Simbolos
VIX_SIMBOLO    = "^VIX"
NASDAQ_SIMBOLO = "^IXIC"
QQQ_SIMBOLO    = "QQQ"    # ETF del NASDAQ — se puede operar
SPY_SIMBOLO    = "SPY"
SQQQ_SIMBOLO   = "SQQQ"   # ETF inverso NASDAQ 3x — sube cuando NASDAQ baja

UMBRALES = {
    "vix_subida_extrema":  20,   # VIX sube mas del 20% — señal muy fuerte
    "vix_subida_alta":     10,   # VIX sube mas del 10% — señal fuerte
    "vix_subida_media":     5,   # VIX sube mas del 5%  — señal media
    "vix_nivel_miedo":     25,   # VIX sobre 25 = miedo en mercado
    "vix_nivel_panico":    35,   # VIX sobre 35 = panico — posible rebote
    "vix_nivel_calma":     15,   # VIX bajo 15 = calma — mercado optimista
    "nasdaq_caida_fuerte": -2.0, # NASDAQ cae mas del 2%
    "nasdaq_caida_media":  -1.0, # NASDAQ cae mas del 1%
}

def obtener_datos_vix_nasdaq(dias: int = 60) -> dict:
    try:
        fin    = datetime.now()
        inicio = fin - timedelta(days=dias)

        vix    = yf.Ticker(VIX_SIMBOLO).history(start=inicio, end=fin)
        nasdaq = yf.Ticker(NASDAQ_SIMBOLO).history(start=inicio, end=fin)
        qqq    = yf.Ticker(QQQ_SIMBOLO).history(start=inicio, end=fin)

        if vix.empty or nasdaq.empty:
            return {"error": "Sin datos"}

        return {
            "vix":    vix,
            "nasdaq": nasdaq,
            "qqq":    qqq,
        }
    except Exception as e:
        return {"error": str(e)}

def analizar_correlacion_historica(datos: dict) -> dict:
    vix    = datos["vix"]["Close"]
    nasdaq = datos["nasdaq"]["Close"]

    # Alinea fechas
    df = pd.DataFrame({"vix": vix, "nasdaq": nasdaq}).dropna()
    if len(df) < 10:
        return {"error": "Sin datos suficientes"}

    # Rendimientos diarios
    vix_ret    = df["vix"].pct_change().dropna()
    nasdaq_ret = df["nasdaq"].pct_change().dropna()

    # Correlacion
    correlacion = round(float(vix_ret.corr(nasdaq_ret)), 3)

    # Dias donde VIX subio mas del 5% y NASDAQ bajo
    vix_sube    = vix_ret > 0.05
    nasdaq_baja = nasdaq_ret < 0

    dias_confirmados = int((vix_sube & nasdaq_baja).sum())
    dias_vix_sube    = int(vix_sube.sum())
    tasa_confirmacion = round(dias_confirmados / dias_vix_sube * 100, 1) if dias_vix_sube > 0 else 0

    # Retorno promedio del NASDAQ cuando VIX sube mas del 5%
    nasdaq_cuando_vix_sube = nasdaq_ret[vix_sube]
    retorno_promedio = round(float(nasdaq_cuando_vix_sube.mean()) * 100, 3) if len(nasdaq_cuando_vix_sube) > 0 else 0

    return {
        "correlacion_vix_nasdaq": correlacion,
        "dias_analizados":        len(df),
        "dias_vix_sube_5pct":     dias_vix_sube,
        "dias_nasdaq_baja_con_vix": dias_confirmados,
        "tasa_confirmacion":      tasa_confirmacion,
        "retorno_promedio_nasdaq_con_vix": retorno_promedio,
    }

def obtener_señal_actual() -> dict:
    try:
        # Datos de hoy
        vix_hoy    = yf.Ticker(VIX_SIMBOLO).history(period="5d", interval="1d")
        nasdaq_hoy = yf.Ticker(NASDAQ_SIMBOLO).history(period="5d", interval="1d")
        qqq_hoy    = yf.Ticker(QQQ_SIMBOLO).history(period="5d", interval="1d")

        if vix_hoy.empty or nasdaq_hoy.empty:
            return {"error": "Sin datos de hoy"}

        # Valores actuales
        vix_actual    = float(vix_hoy["Close"].iloc[-1])
        vix_ayer      = float(vix_hoy["Close"].iloc[-2]) if len(vix_hoy) > 1 else vix_actual
        nasdaq_actual = float(nasdaq_hoy["Close"].iloc[-1])
        nasdaq_ayer   = float(nasdaq_hoy["Close"].iloc[-2]) if len(nasdaq_hoy) > 1 else nasdaq_actual
        qqq_actual    = float(qqq_hoy["Close"].iloc[-1]) if not qqq_hoy.empty else 0
        qqq_ayer      = float(qqq_hoy["Close"].iloc[-2]) if len(qqq_hoy) > 1 else qqq_actual

        # Cambios porcentuales
        vix_cambio_pct    = round(((vix_actual - vix_ayer) / vix_ayer) * 100, 3)
        nasdaq_cambio_pct = round(((nasdaq_actual - nasdaq_ayer) / nasdaq_ayer) * 100, 3)
        qqq_cambio_pct    = round(((qqq_actual - qqq_ayer) / qqq_ayer) * 100, 3)

        # Nivel de VIX
        if vix_actual >= UMBRALES["vix_nivel_panico"]:
            nivel_vix = "PANICO"
        elif vix_actual >= UMBRALES["vix_nivel_miedo"]:
            nivel_vix = "MIEDO"
        elif vix_actual <= UMBRALES["vix_nivel_calma"]:
            nivel_vix = "CALMA"
        else:
            nivel_vix = "NORMAL"

        # Señal principal
        señal    = "ESPERAR"
        fuerza   = "baja"
        accion   = "ESPERAR"
        razon    = ""
        puntos   = 0

        # VIX subiendo + NASDAQ bajando = VENDER QQQ / COMPRAR SQQQ
        if vix_cambio_pct >= UMBRALES["vix_subida_extrema"]:
            puntos += 4
            razon  += f"VIX +{vix_cambio_pct}% SUBIDA EXTREMA. "
        elif vix_cambio_pct >= UMBRALES["vix_subida_alta"]:
            puntos += 3
            razon  += f"VIX +{vix_cambio_pct}% subida alta. "
        elif vix_cambio_pct >= UMBRALES["vix_subida_media"]:
            puntos += 2
            razon  += f"VIX +{vix_cambio_pct}% subida media. "

        if nasdaq_cambio_pct <= UMBRALES["nasdaq_caida_fuerte"]:
            puntos += 2
            razon  += f"NASDAQ {nasdaq_cambio_pct}% caida fuerte. "
        elif nasdaq_cambio_pct <= UMBRALES["nasdaq_caida_media"]:
            puntos += 1
            razon  += f"NASDAQ {nasdaq_cambio_pct}% caida. "

        if nivel_vix in ["MIEDO", "PANICO"]:
            puntos += 1
            razon  += f"Nivel VIX={nivel_vix}. "

        # VIX bajando desde panico = posible rebote NASDAQ = COMPRAR QQQ
        puntos_compra = 0
        razon_compra  = ""
        if vix_cambio_pct <= -10 and nivel_vix == "PANICO":
            puntos_compra += 4
            razon_compra  += f"VIX cae {vix_cambio_pct}% desde PANICO — rebote NASDAQ probable. "
        elif vix_cambio_pct <= -5 and vix_actual > UMBRALES["vix_nivel_miedo"]:
            puntos_compra += 2
            razon_compra  += f"VIX cae {vix_cambio_pct}% desde zona miedo. "

        if puntos >= 5:
            señal  = "VENDER_QQQ"
            accion = "VENDER"
            fuerza = "muy_alta"
        elif puntos >= 3:
            señal  = "VENDER_QQQ"
            accion = "VENDER"
            fuerza = "alta"
        elif puntos >= 2:
            señal  = "PRECAUCION_VENTA"
            accion = "VENDER"
            fuerza = "media"
        elif puntos_compra >= 4:
            señal  = "COMPRAR_QQQ_REBOTE"
            accion = "COMPRAR"
            fuerza = "alta"
            razon  = razon_compra
        elif puntos_compra >= 2:
            señal  = "POSIBLE_REBOTE"
            accion = "COMPRAR"
            fuerza = "media"
            razon  = razon_compra

        # Stop loss y take profit para QQQ
        atr_qqq = abs(qqq_actual - qqq_ayer)
        if accion == "VENDER":
            sl  = round(qqq_actual * 1.02, 2)
            tp1 = round(qqq_actual * 0.97, 2)
            tp2 = round(qqq_actual * 0.95, 2)
        elif accion == "COMPRAR":
            sl  = round(qqq_actual * 0.98, 2)
            tp1 = round(qqq_actual * 1.03, 2)
            tp2 = round(qqq_actual * 1.05, 2)
        else:
            sl = tp1 = tp2 = 0

        return {
            "vix_actual":       round(vix_actual, 2),
            "vix_cambio_pct":   vix_cambio_pct,
            "nivel_vix":        nivel_vix,
            "nasdaq_actual":    round(nasdaq_actual, 2),
            "nasdaq_cambio_pct":nasdaq_cambio_pct,
            "qqq_actual":       round(qqq_actual, 2),
            "qqq_cambio_pct":   qqq_cambio_pct,
            "señal":            señal,
            "accion":           accion,
            "fuerza":           fuerza,
            "puntos":           puntos,
            "razon":            razon.strip(),
            "stop_loss":        sl,
            "take_profit_1":    tp1,
            "take_profit_2":    tp2,
            "timestamp":        datetime.now().strftime("%H:%M:%S"),
        }
    except Exception as e:
        return {"error": str(e)}

def analizar_vix_nasdaq_completo() -> dict:
    print("[agente_vix] Obteniendo datos historicos...")
    datos = obtener_datos_vix_nasdaq(dias=90)

    if "error" in datos:
        return datos

    print("[agente_vix] Analizando correlacion historica...")
    correlacion = analizar_correlacion_historica(datos)

    print("[agente_vix] Obteniendo señal actual...")
    señal_actual = obtener_señal_actual()

    return {
        "correlacion_historica": correlacion,
        "señal_actual":          señal_actual,
        "timestamp":             datetime.now().strftime("%H:%M:%S"),
    }

def obtener_reporte_vix_nasdaq() -> str:
    resultado = analizar_vix_nasdaq_completo()
    señal     = resultado.get("señal_actual", {})
    corr      = resultado.get("correlacion_historica", {})
    return (
        f"VIX={señal.get('vix_actual','N/A')} ({señal.get('vix_cambio_pct','N/A')}%) {señal.get('nivel_vix','N/A')} | "
        f"NASDAQ={señal.get('nasdaq_cambio_pct','N/A')}% | "
        f"Señal={señal.get('señal','N/A')} ({señal.get('fuerza','N/A')}) | "
        f"Tasa confirmacion historica={corr.get('tasa_confirmacion','N/A')}%"
    )