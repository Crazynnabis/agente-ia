# agente_financiero/agente_fundamental.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import yfinance as yf
from nucleo.cliente_ia import chat

ACTIVOS = ["AAPL", "NVDA", "MSFT", "TSLA", "SPY", "AMZN", "GOOGL", "META"]

def obtener_fundamentales(simbolo: str) -> dict:
    try:
        info = yf.Ticker(simbolo).info
        precio_actual  = info.get("currentPrice")
        precio_objetivo = info.get("targetMeanPrice")
        upside = round(((precio_objetivo / precio_actual) - 1) * 100, 1) if precio_actual and precio_objetivo else None
        return {
            "simbolo":               simbolo,
            "sector":                info.get("sector", "N/A"),
            "pe_ratio":              info.get("trailingPE"),
            "pe_forward":            info.get("forwardPE"),
            "margen_beneficio":      info.get("profitMargins"),
            "deuda_equity":          info.get("debtToEquity"),
            "crecimiento_earnings":  info.get("earningsGrowth"),
            "recomendacion":         info.get("recommendationKey"),
            "precio_actual":         precio_actual,
            "precio_objetivo":       precio_objetivo,
            "upside":                upside,
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

async def analizar_fundamental_completo() -> dict:
    todos = []
    for simbolo in ACTIVOS:
        print(f"[agente_fundamental] Analizando {simbolo}...")
        todos.append(obtener_fundamentales(simbolo))

    resumen = "\n".join([
        f"{f['simbolo']}: PE={f.get('pe_ratio','N/A')} | PE_fwd={f.get('pe_forward','N/A')} | margen={f.get('margen_beneficio','N/A')} | deuda={f.get('deuda_equity','N/A')} | crec={f.get('crecimiento_earnings','N/A')} | recom={f.get('recomendacion','N/A')} | upside={f.get('upside','N/A')}%"
        for f in todos if "error" not in f
    ])

    print("[agente_fundamental] Analizando con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": "DATOS FUNDAMENTALES:\n" + resumen}],
        system="Eres un analista fundamental experto. Analiza los datos y entrega: 1) Top 3 empresas infravaloradas 2) Mejor salud financiera 3) Mayor crecimiento 4) Sobrevaloradas — precaución 5) Recomendacion comprar/mantener/evitar por empresa. Responde en español conciso y accionable.",
        max_tokens=800
    )

    return {
        "fundamentales": todos,
        "analisis":      respuesta["texto"],
        "modelo":        respuesta["modelo"]
    }

async def obtener_reporte_fundamental() -> str:
    resultado = await analizar_fundamental_completo()
    return resultado.get("analisis", "Sin análisis fundamental")