# agente_financiero/agente_historico.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from nucleo.cliente_ia import chat

ACTIVOS = {
    "acciones": ["AAPL", "NVDA", "MSFT", "TSLA", "SPY", "QQQ"],
    "crypto":   ["BTC-USD", "ETH-USD"],
    "materias": ["GC=F", "CL=F"],
}

def obtener_datos_historicos(simbolo: str, anos: int = 3) -> pd.DataFrame:
    try:
        fin    = datetime.now()
        inicio = fin - timedelta(days=365 * anos)
        return yf.Ticker(simbolo).history(start=inicio, end=fin)
    except Exception as e:
        print(f"[agente_historico] Error {simbolo}: {e}")
        return pd.DataFrame()

def calcular_estadisticas(df: pd.DataFrame, simbolo: str) -> dict:
    if df.empty:
        return {"simbolo": simbolo, "error": "Sin datos"}
    precios     = df["Close"]
    rendimientos = precios.pct_change().dropna()
    rend_1m  = ((precios.iloc[-1] / precios.iloc[-22])  - 1) * 100 if len(precios) > 22  else None
    rend_1a  = ((precios.iloc[-1] / precios.iloc[-252]) - 1) * 100 if len(precios) > 252 else None
    volatilidad = rendimientos.std() * np.sqrt(252) * 100
    rolling_max = precios.cummax()
    max_drawdown = (((precios - rolling_max) / rolling_max) * 100).min()
    return {
        "simbolo":          simbolo,
        "precio_actual":    round(float(precios.iloc[-1]), 2),
        "rend_1m":          round(float(rend_1m), 2) if rend_1m else None,
        "rend_1a":          round(float(rend_1a), 2) if rend_1a else None,
        "volatilidad_anual":round(float(volatilidad), 2),
        "max_drawdown":     round(float(max_drawdown), 2),
    }

def detectar_patrones(df: pd.DataFrame, simbolo: str) -> dict:
    if df.empty or len(df) < 50:
        return {"simbolo": simbolo, "patron": "Sin datos"}
    precios = df["Close"]
    ma50    = float(precios.rolling(50).mean().iloc[-1])
    ma200   = float(precios.rolling(200).mean().iloc[-1]) if len(precios) >= 200 else None
    precio  = float(precios.iloc[-1])
    patron  = "neutral"
    if ma200:
        if ma50 > ma200 and precio > ma50:
            patron = "GOLDEN CROSS alcista"
        elif ma50 < ma200 and precio < ma50:
            patron = "DEATH CROSS bajista"
    return {"simbolo": simbolo, "ma50": round(ma50, 2), "ma200": round(ma200, 2) if ma200 else None, "patron": patron}

async def analizar_historico_completo() -> dict:
    todos_stats    = []
    todos_patrones = []
    todos_simbolos = ACTIVOS["acciones"] + ACTIVOS["crypto"] + ACTIVOS["materias"]

    for simbolo in todos_simbolos:
        print(f"[agente_historico] Analizando {simbolo}...")
        df = obtener_datos_historicos(simbolo)
        todos_stats.append(calcular_estadisticas(df, simbolo))
        todos_patrones.append(detectar_patrones(df, simbolo))

    resumen_stats = "\n".join([
        f"{s['simbolo']}: precio={s.get('precio_actual','N/A')} | 1m={s.get('rend_1m','N/A')}% | 1a={s.get('rend_1a','N/A')}% | vol={s.get('volatilidad_anual','N/A')}% | drawdown={s.get('max_drawdown','N/A')}%"
        for s in todos_stats if "error" not in s
    ])
    resumen_patrones = "\n".join([
        f"{p['simbolo']}: {p.get('patron','N/A')}"
        for p in todos_patrones
    ])

    print("[agente_historico] Generando análisis con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"ESTADÍSTICAS:\n{resumen_stats}\n\nPATRONES:\n{resumen_patrones}"}],
        system="""Eres un analista cuantitativo experto en datos históricos.
Analiza y entrega:
1. Top 3 activos con mejor perfil riesgo/retorno
2. Activos en tendencia alcista confirmada
3. Activos en tendencia bajista — evitar
4. Oportunidades detectadas
5. Riesgos detectados
6. Recomendación de asignación de portafolio
Responde en español, conciso y accionable.""",
        max_tokens=800
    )

    return {
        "estadisticas": todos_stats,
        "patrones":     todos_patrones,
        "analisis":     respuesta["texto"],
        "modelo":       respuesta["modelo"]
    }

async def obtener_reporte_historico() -> str:
    resultado = await analizar_historico_completo()
    return resultado.get("analisis", "Sin análisis histórico")