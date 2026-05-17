# agente_financiero/agente_estacionalidad.py
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

ACTIVOS = {
    "BTC-USD":  "BTCUSDT",
    "ETH-USD":  "ETHUSDT",
    "SPY":      "SPY",
    "QQQ":      "QQQ",
    "GC=F":     "ORO",
}

# Patrones estacionales conocidos
PATRONES_CONOCIDOS = {
    1:  {"nombre": "Enero",      "bitcoin": "alcista",  "acciones": "alcista",  "razon": "Enero Effect — fondos reinvierten capital nuevo año"},
    2:  {"nombre": "Febrero",    "bitcoin": "neutral",  "acciones": "neutral",  "razon": "Consolidacion post-enero"},
    3:  {"nombre": "Marzo",      "bitcoin": "alcista",  "acciones": "neutral",  "razon": "Fin de trimestre — rebalanceo fondos"},
    4:  {"nombre": "Abril",      "bitcoin": "alcista",  "acciones": "alcista",  "razon": "Abril historicamente alcista para crypto y acciones"},
    5:  {"nombre": "Mayo",       "bitcoin": "bajista",  "acciones": "bajista",  "razon": "Sell in May and go away — patron historico fuerte"},
    6:  {"nombre": "Junio",      "bitcoin": "bajista",  "acciones": "bajista",  "razon": "Continuacion tendencia bajista mayo"},
    7:  {"nombre": "Julio",      "bitcoin": "alcista",  "acciones": "alcista",  "razon": "Recuperacion verano — fondos regresan al mercado"},
    8:  {"nombre": "Agosto",     "bitcoin": "neutral",  "acciones": "neutral",  "razon": "Verano — bajo volumen institucional"},
    9:  {"nombre": "Septiembre", "bitcoin": "bajista",  "acciones": "bajista",  "razon": "Septiembre es historicamente el peor mes del año"},
    10: {"nombre": "Octubre",    "bitcoin": "alcista",  "acciones": "neutral",  "razon": "Uptober — octubre historicamente alcista para BTC"},
    11: {"nombre": "Noviembre",  "bitcoin": "alcista",  "acciones": "alcista",  "razon": "Pre-diciembre rally — fondos cierran año con fuerza"},
    12: {"nombre": "Diciembre",  "bitcoin": "alcista",  "acciones": "alcista",  "razon": "Santa Rally — diciembre historicamente alcista"},
}

# Ciclos de halving de Bitcoin
HALVINGS = [
    datetime(2012, 11, 28),
    datetime(2016, 7, 9),
    datetime(2020, 5, 11),
    datetime(2024, 4, 19),  # Ultimo halving
]
PROXIMO_HALVING = datetime(2028, 4, 1)  # Estimado

def calcular_rendimientos_historicos(simbolo: str, años: int = 5) -> dict:
    try:
        fin    = datetime.now()
        inicio = fin - timedelta(days=365 * años)
        df = yf.Ticker(simbolo).history(start=inicio, end=fin)
        if df.empty:
            return {}

        df["mes"]       = df.index.month
        df["año"]       = df.index.year
        df["rendimiento"]= df["Close"].pct_change()

        # Rendimiento promedio por mes historicamente
        rendimiento_mes = {}
        for mes in range(1, 13):
            datos_mes = df[df["mes"] == mes]["rendimiento"].dropna()
            if len(datos_mes) > 0:
                rendimiento_mes[mes] = {
                    "promedio":    round(float(datos_mes.mean()) * 100, 2),
                    "positivos":   int((datos_mes > 0).sum()),
                    "negativos":   int((datos_mes < 0).sum()),
                    "win_rate":    round(float((datos_mes > 0).mean()) * 100, 1),
                }

        return rendimiento_mes
    except Exception as e:
        return {}

def analizar_ciclo_halving() -> dict:
    ahora = datetime.now()

    # Dias desde ultimo halving
    ultimo_halving  = HALVINGS[-1]
    dias_desde_halving = (ahora - ultimo_halving).days
    dias_para_proximo  = (PROXIMO_HALVING - ahora).days

    # Fase del ciclo (ciclo de 4 años = ~1460 dias)
    ciclo_pct = round((dias_desde_halving / 1460) * 100, 1)

    if ciclo_pct < 25:
        fase = "POST_HALVING_TEMPRANO"
        sesgo = "MUY_ALCISTA"
        razon = f"Primeros 6 meses post-halving — historicamente la fase mas alcista"
    elif ciclo_pct < 50:
        fase = "BULL_MARKET"
        sesgo = "ALCISTA"
        razon = f"Bull market maduro — precio tipicamente en maximos historicos"
    elif ciclo_pct < 75:
        fase = "POST_ATH_CORRECION"
        sesgo = "BAJISTA"
        razon = f"Fase de correccion post-ATH — tipicamente -70% a -80%"
    else:
        fase = "PRE_HALVING_ACUMULACION"
        sesgo = "NEUTRAL_ALCISTA"
        razon = f"Acumulacion pre-halving — smart money comprando antes del evento"

    return {
        "ultimo_halving":       ultimo_halving.strftime("%Y-%m-%d"),
        "dias_desde_halving":   dias_desde_halving,
        "proximo_halving":      PROXIMO_HALVING.strftime("%Y-%m-%d"),
        "dias_para_proximo":    dias_para_proximo,
        "ciclo_pct":            ciclo_pct,
        "fase":                 fase,
        "sesgo":                sesgo,
        "razon":                razon,
    }

def analizar_estacionalidad_completo() -> dict:
    ahora = datetime.now()
    mes_actual = ahora.month
    patron_mes = PATRONES_CONOCIDOS.get(mes_actual, {})
    ciclo_halving = analizar_ciclo_halving()

    # Rendimientos historicos reales
    print("[agente_estacionalidad] Calculando rendimientos historicos BTC...")
    rend_btc = calcular_rendimientos_historicos("BTC-USD", años=5)

    print("[agente_estacionalidad] Calculando rendimientos historicos SPY...")
    rend_spy = calcular_rendimientos_historicos("SPY", años=5)

    # Datos del mes actual
    rend_btc_mes = rend_btc.get(mes_actual, {})
    rend_spy_mes = rend_spy.get(mes_actual, {})

    # Señal combinada
    sesgo_mes     = patron_mes.get("bitcoin", "neutral")
    sesgo_halving = ciclo_halving["sesgo"]

    if "ALCISTA" in sesgo_halving and sesgo_mes == "alcista":
        señal_final = "MUY_ALCISTA"
        confianza   = 85
    elif "ALCISTA" in sesgo_halving or sesgo_mes == "alcista":
        señal_final = "ALCISTA"
        confianza   = 65
    elif "BAJISTA" in sesgo_halving and sesgo_mes == "bajista":
        señal_final = "MUY_BAJISTA"
        confianza   = 85
    elif sesgo_mes == "bajista":
        señal_final = "BAJISTA"
        confianza   = 65
    else:
        señal_final = "NEUTRAL"
        confianza   = 50

    return {
        "mes_actual":         ahora.strftime("%B %Y"),
        "patron_mes":         patron_mes,
        "ciclo_halving":      ciclo_halving,
        "rend_historico_btc": rend_btc_mes,
        "rend_historico_spy": rend_spy_mes,
        "señal_estacional":   señal_final,
        "confianza":          confianza,
        "razon_mes":          patron_mes.get("razon", ""),
        "razon_halving":      ciclo_halving["razon"],
        "timestamp":          datetime.now().strftime("%H:%M:%S"),
    }

def obtener_reporte_estacionalidad() -> str:
    r = analizar_estacionalidad_completo()
    return (
        f"Estacionalidad {r['mes_actual']}: {r['señal_estacional']} ({r['confianza']}%) | "
        f"Mes={r['patron_mes'].get('bitcoin','N/A')} | "
        f"Halving={r['ciclo_halving']['fase']} ({r['ciclo_halving']['ciclo_pct']}%) | "
        f"{r['razon_mes']}"
    )