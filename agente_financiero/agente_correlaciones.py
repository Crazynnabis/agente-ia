# agente_financiero/agente_correlaciones.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import yfinance as yf
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from nucleo.cliente_ia import chat

# Grupos de activos correlacionados
GRUPOS = {
    "crypto":      ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"],
    "tech":        ["AAPL", "NVDA", "MSFT", "GOOGL", "META", "AMZN"],
    "indices":     ["SPY", "QQQ", "DIA"],
    "commodities": ["GC=F", "CL=F", "SI=F"],
    "forex":       ["DX-Y.NYB"],  # Indice dolar
}

# Correlaciones conocidas para contexto
CORRELACIONES_CONOCIDAS = {
    "BTC-USD_ETH-USD":   {"correlacion_esperada": 0.85, "relacion": "BTC lidera, ETH sigue con 2-4h de retraso"},
    "SPY_QQQ":           {"correlacion_esperada": 0.95, "relacion": "QQQ amplifica movimientos de SPY"},
    "GC=F_DX-Y.NYB":    {"correlacion_esperada": -0.7, "relacion": "Oro sube cuando dolar baja"},
    "CL=F_DX-Y.NYB":    {"correlacion_esperada": -0.5, "relacion": "Petroleo tiende a bajar con dolar fuerte"},
    "BTC-USD_SPY":       {"correlacion_esperada": 0.4,  "relacion": "Correlacion moderada en crisis de liquidez"},
}

def obtener_datos_multiples(simbolos: list, dias: int = 60) -> pd.DataFrame:
    fin    = datetime.now()
    inicio = fin - timedelta(days=dias)
    dfs = {}
    for simbolo in simbolos:
        try:
            ticker = yf.Ticker(simbolo)
            df = ticker.history(start=inicio, end=fin)
            if not df.empty:
                dfs[simbolo] = df["Close"]
        except Exception as e:
            print(f"[agente_correlaciones] Error {simbolo}: {e}")
    if not dfs:
        return pd.DataFrame()
    combined = pd.DataFrame(dfs)
    # Rellena fines de semana con ultimo precio disponible
    combined = combined.ffill().bfill()
    combined = combined.dropna()
    return combined

def calcular_matriz_correlacion(df: pd.DataFrame) -> pd.DataFrame:
    rendimientos = df.pct_change().dropna()
    return rendimientos.corr()

def detectar_divergencias(df: pd.DataFrame, par: tuple) -> dict:
    if len(par) != 2 or par[0] not in df.columns or par[1] not in df.columns:
        return {}
    s1 = df[par[0]].pct_change().dropna()
    s2 = df[par[1]].pct_change().dropna()
    correlacion_historica = float(s1.corr(s2))
    correlacion_reciente  = float(s1[-10:].corr(s2[-10:]))
    divergencia = correlacion_historica - correlacion_reciente
    estado = "normal"
    if abs(divergencia) > 0.3:
        if divergencia > 0:
            estado = "DIVERGENCIA — correlacion rompio a la baja, posible oportunidad"
        else:
            estado = "CONVERGENCIA — correlacion aumentando, movimiento conjunto esperado"
    return {
        "par":                   f"{par[0]}/{par[1]}",
        "correlacion_historica": round(correlacion_historica, 3),
        "correlacion_reciente":  round(correlacion_reciente, 3),
        "divergencia":           round(divergencia, 3),
        "estado":                estado,
    }

def detectar_lider_seguidor(df: pd.DataFrame, simbolo_a: str, simbolo_b: str) -> dict:
    if simbolo_a not in df.columns or simbolo_b not in df.columns:
        return {}
    rend_a = df[simbolo_a].pct_change().dropna()
    rend_b = df[simbolo_b].pct_change().dropna()
    correlaciones_lag = {}
    for lag in range(0, 6):
        if lag == 0:
            corr = float(rend_a.corr(rend_b))
        else:
            corr = float(rend_a[:-lag].corr(rend_b[lag:]))
        correlaciones_lag[lag] = round(corr, 3)
    mejor_lag = max(correlaciones_lag, key=lambda x: abs(correlaciones_lag[x]))
    if mejor_lag == 0:
        relacion = "movimiento_simultaneo"
    elif correlaciones_lag[mejor_lag] > 0:
        relacion = f"{simbolo_a}_lidera_{simbolo_b}_por_{mejor_lag}_periodos"
    else:
        relacion = f"relacion_inversa_con_{mejor_lag}_periodos_lag"
    return {
        "par":          f"{simbolo_a}/{simbolo_b}",
        "mejor_lag":    mejor_lag,
        "correlacion":  correlaciones_lag[mejor_lag],
        "relacion":     relacion,
        "lags":         correlaciones_lag,
    }

async def analizar_correlaciones_completo() -> dict:
    print("[agente_correlaciones] Descargando datos...")
    todos_simbolos = []
    for grupo in GRUPOS.values():
        todos_simbolos.extend(grupo)
    todos_simbolos = list(set(todos_simbolos))

    df = obtener_datos_multiples(todos_simbolos, dias=60)
    if df.empty:
        return {"error": "Sin datos disponibles"}

    print("[agente_correlaciones] Calculando matriz de correlacion...")
    matriz = calcular_matriz_correlacion(df)

    # Detecta pares con alta correlacion
    pares_alta_corr = []
    cols = list(matriz.columns)
    for i in range(len(cols)):
        for j in range(i+1, len(cols)):
            corr = float(matriz.iloc[i, j])
            if abs(corr) > 0.7:
                pares_alta_corr.append({
                    "par":         f"{cols[i]}/{cols[j]}",
                    "correlacion": round(corr, 3),
                    "tipo":        "positiva" if corr > 0 else "negativa",
                })

    # Analiza divergencias en pares clave
    print("[agente_correlaciones] Detectando divergencias...")
    divergencias = []
    pares_analizar = [
        ("BTC-USD", "ETH-USD"),
        ("SPY", "QQQ"),
        ("BTC-USD", "SPY"),
        ("GC=F", "DX-Y.NYB"),
    ]
    for par in pares_analizar:
        if par[0] in df.columns and par[1] in df.columns:
            div = detectar_divergencias(df, par)
            if div:
                divergencias.append(div)

    # Detecta lideres y seguidores
    print("[agente_correlaciones] Analizando lider/seguidor...")
    lider_seguidor = []
    for par in [("BTC-USD", "ETH-USD"), ("SPY", "QQQ")]:
        if par[0] in df.columns and par[1] in df.columns:
            ls = detectar_lider_seguidor(df, par[0], par[1])
            if ls:
                lider_seguidor.append(ls)

    # Resumen para IA
    resumen_pares = "\n".join([
        f"{p['par']}: correlacion={p['correlacion']} ({p['tipo']})"
        for p in sorted(pares_alta_corr, key=lambda x: abs(x["correlacion"]), reverse=True)[:10]
    ])
    resumen_div = "\n".join([
        f"{d['par']}: hist={d['correlacion_historica']} reciente={d['correlacion_reciente']} estado={d['estado']}"
        for d in divergencias
    ])
    resumen_ls = "\n".join([
        f"{l['par']}: {l['relacion']} correlacion={l['correlacion']}"
        for l in lider_seguidor
    ])

    print("[agente_correlaciones] Generando analisis con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"CORRELACIONES ALTAS:\n{resumen_pares}\n\nDIVERGENCIAS:\n{resumen_div}\n\nLIDER/SEGUIDOR:\n{resumen_ls}"}],
        system="""Eres un analista experto en correlaciones de mercados financieros.
Analiza las correlaciones y entrega:
1. Oportunidades de arbitraje o anticipacion detectadas
2. Activos que estan divergiendo de su correlacion historica
3. Cual activo lidera y cual sigue — y cuanto tiempo de anticipacion da
4. Como usar estas correlaciones para mejorar las entradas de trading
5. Alertas de correlaciones rotas que indican movimiento inminente
Responde en español, conciso y accionable para trading.""",
        max_tokens=800
    )

    return {
        "pares_alta_correlacion": pares_alta_corr,
        "divergencias":           divergencias,
        "lider_seguidor":         lider_seguidor,
        "analisis":               respuesta["texto"],
        "modelo":                 respuesta["modelo"],
        "timestamp":              datetime.now().strftime("%H:%M:%S"),
    }

def obtener_reporte_correlaciones() -> str:
    return asyncio.run(analizar_correlaciones_completo()).get("analisis", "Sin analisis")