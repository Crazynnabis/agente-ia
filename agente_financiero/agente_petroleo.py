# agente_financiero/agente_petroleo.py
import requests
import yfinance as yf
import numpy as np
import pandas as pd
import ollama
from datetime import datetime, timedelta
from firecrawl import FirecrawlApp
import os
from dotenv import load_dotenv

load_dotenv()

# Activos relacionados con petróleo
ACTIVOS_PETROLEO = {
    "futuros": {
        "WTI":   "CL=F",   # West Texas Intermediate
        "Brent": "BZ=F",   # Brent Crude
        "Gas":   "NG=F",   # Natural Gas
    },
    "empresas": {
        "Exxon":      "XOM",
        "Chevron":    "CVX",
        "Occidental": "OXY",
        "Schlumberger":"SLB",
        "ConocoPhil": "COP",
        "Halliburton":"HAL",
        "Pioneer":    "PXD",
    },
    "etfs": {
        "Oil_ETF":    "USO",
        "Energy_ETF": "XLE",
        "OilGas_ETF": "XOP",
    }
}

FUENTES_NOTICIAS_PETROLEO = [
    "https://oilprice.com/latest-energy-news/world-news/",
    "https://www.reuters.com/business/energy/",
]

def obtener_precio_petroleo() -> dict:
    try:
        precios = {}
        for nombre, simbolo in ACTIVOS_PETROLEO["futuros"].items():
            ticker = yf.Ticker(simbolo)
            info   = ticker.history(period="5d", interval="1d")
            if not info.empty:
                precio_actual  = float(info["Close"].iloc[-1])
                precio_ayer    = float(info["Close"].iloc[-2]) if len(info) > 1 else precio_actual
                cambio_pct     = round(((precio_actual - precio_ayer) / precio_ayer) * 100, 3)
                precio_semana  = float(info["Close"].iloc[0])
                cambio_semana  = round(((precio_actual - precio_semana) / precio_semana) * 100, 3)
                precios[nombre] = {
                    "precio":        round(precio_actual, 2),
                    "cambio_dia":    cambio_pct,
                    "cambio_semana": cambio_semana,
                    "volumen":       int(info["Volume"].iloc[-1]),
                }
        return precios
    except Exception as e:
        return {"error": str(e)}

def obtener_empresas_petroleo() -> list:
    empresas = []
    for nombre, simbolo in ACTIVOS_PETROLEO["empresas"].items():
        try:
            ticker = yf.Ticker(simbolo)
            info   = ticker.info
            hist   = ticker.history(period="5d")
            if hist.empty:
                continue
            precio_actual = float(hist["Close"].iloc[-1])
            precio_ayer   = float(hist["Close"].iloc[-2]) if len(hist) > 1 else precio_actual
            cambio_pct    = round(((precio_actual - precio_ayer) / precio_ayer) * 100, 3)
            empresas.append({
                "nombre":        nombre,
                "simbolo":       simbolo,
                "precio":        round(precio_actual, 2),
                "cambio_dia":    cambio_pct,
                "pe_ratio":      info.get("trailingPE", None),
                "dividend_yield":info.get("dividendYield", None),
                "recomendacion": info.get("recommendationKey", None),
                "sector":        info.get("sector", "Energy"),
            })
        except Exception as e:
            print(f"[agente_petroleo] Error {simbolo}: {e}")
    return empresas

def obtener_inventarios_eia() -> dict:
    try:
        app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
        r   = app.scrape(
            "https://www.eia.gov/petroleum/supply/weekly/",
            formats=["markdown"]
        )
        return {"datos": r.markdown[:2000]}
    except Exception as e:
        return {"error": str(e)}

def obtener_noticias_petroleo() -> str:
    try:
        from newsapi import NewsApiClient
        cliente = NewsApiClient(api_key=os.getenv("NEWS_API_KEY"))
        queries = ["oil price OPEC", "crude oil production", "petroleum market"]
        noticias = []
        for q in queries:
            r = cliente.get_everything(q=q, language="en", sort_by="publishedAt", page_size=3)
            for a in r.get("articles", []):
                noticias.append(f"- {a['title']} ({a['source']['name']})")
        return "\n".join(noticias[:10])
    except Exception as e:
        return f"Error noticias: {e}"

def analizar_correlacion_petroleo_mercado() -> dict:
    try:
        fin    = datetime.now()
        inicio = fin - timedelta(days=90)
        simbolos = ["CL=F", "SPY", "XLE", "DX-Y.NYB", "GC=F"]
        dfs = {}
        for s in simbolos:
            df = yf.Ticker(s).history(start=inicio, end=fin)
            if not df.empty:
                dfs[s] = df["Close"]

        combined = pd.DataFrame(dfs).ffill().bfill().dropna()
        correlaciones = {}
        if "CL=F" in combined.columns:
            for col in combined.columns:
                if col != "CL=F":
                    corr = float(combined["CL=F"].corr(combined[col]))
                    correlaciones[col] = round(corr, 3)

        impacto = []
        if correlaciones.get("SPY", 0) > 0.5:
            impacto.append("Petroleo correlacionado positivamente con bolsa — subida de petroleo favorece acciones energia")
        if correlaciones.get("DX-Y.NYB", 0) < -0.3:
            impacto.append("Petroleo correlacion negativa con dolar — dolar fuerte presiona petroleo a la baja")
        if correlaciones.get("GC=F", 0) > 0.4:
            impacto.append("Petroleo correlacionado con oro — ambos activos refugio en tensiones geopoliticas")

        return {
            "correlaciones":    correlaciones,
            "impacto_mercado":  impacto,
        }
    except Exception as e:
        return {"error": str(e)}

async def analizar_petroleo_completo() -> dict:
    print("[agente_petroleo] Obteniendo precios futuros...")
    precios = obtener_precio_petroleo()

    print("[agente_petroleo] Analizando empresas petroleras...")
    empresas = obtener_empresas_petroleo()

    print("[agente_petroleo] Obteniendo noticias...")
    noticias = obtener_noticias_petroleo()

    print("[agente_petroleo] Analizando correlaciones...")
    correlaciones = analizar_correlacion_petroleo_mercado()

    # Resumen para IA
    resumen_precios = "\n".join([
        f"{nombre}: ${datos.get('precio','N/A')} | dia={datos.get('cambio_dia','N/A')}% | semana={datos.get('cambio_semana','N/A')}%"
        for nombre, datos in precios.items() if "error" not in datos
    ]) if "error" not in precios else "Sin datos de precios"

    resumen_empresas = "\n".join([
        f"{e['nombre']} ({e['simbolo']}): ${e['precio']} | {e['cambio_dia']}% | recom={e['recomendacion']}"
        for e in empresas
    ])

    resumen_corr = "\n".join([
        f"CL=F vs {k}: {v}"
        for k, v in correlaciones.get("correlaciones", {}).items()
    ])

    contexto = f"""
PRECIOS PETROLEO:
{resumen_precios}

EMPRESAS PETROLERAS EN BOLSA:
{resumen_empresas}

NOTICIAS:
{noticias[:1000]}

CORRELACIONES (90 dias):
{resumen_corr}

IMPACTO EN MERCADO:
{chr(10).join(correlaciones.get('impacto_mercado', []))}
"""

    print("[agente_petroleo] Generando analisis con IA...")
    from nucleo.cliente_ia import chat
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"Analiza el mercado petrolero:\n{contexto}"}],
        system="""Eres un analista experto en mercados de energia y petroleo.
Analiza los datos y entrega:
1. Estado actual del mercado petrolero (alcista/bajista/lateral)
2. Factores que impulsan el precio (OPEC, geopolitica, inventarios, demanda)
3. Impacto en bolsa de valores (sectores favorecidos/perjudicados)
4. Empresas petroleras con mejor oportunidad de inversion
5. Prediccion de movimiento proximas 48 horas
6. Nivel de riesgo energetico global: BAJO/MEDIO/ALTO
Responde en espanol, conciso y accionable.""",
        max_tokens=800
    )

    return {
        "precios":      precios,
        "empresas":     empresas,
        "correlaciones":correlaciones,
        "analisis":     respuesta["texto"],
        "modelo":       respuesta["modelo"],
        "timestamp":    datetime.now().strftime("%H:%M:%S"),
    }

def obtener_reporte_petroleo() -> str:
    import asyncio
    resultado = asyncio.run(analizar_petroleo_completo())
    return resultado.get("analisis", "Sin analisis de petroleo")