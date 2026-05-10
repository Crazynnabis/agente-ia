import yfinance as yf
import ollama
from firecrawl import FirecrawlApp
import os
from dotenv import load_dotenv

load_dotenv()

ACTIVOS = ["AAPL", "NVDA", "MSFT", "TSLA", "SPY", "AMZN", "GOOGL", "META"]

def obtener_fundamentales(simbolo: str) -> dict:
    try:
        ticker = yf.Ticker(simbolo)
        info = ticker.info
        return {
            "simbolo": simbolo,
            "sector": info.get("sector", "N/A"),
            "pe_ratio": info.get("trailingPE", None),
            "pe_forward": info.get("forwardPE", None),
            "margen_beneficio": info.get("profitMargins", None),
            "deuda_equity": info.get("debtToEquity", None),
            "crecimiento_earnings": info.get("earningsGrowth", None),
            "recomendacion_analistas": info.get("recommendationKey", None),
            "precio_objetivo": info.get("targetMeanPrice", None),
            "precio_actual": info.get("currentPrice", None),
        }
    except Exception as e:
        return {"simbolo": simbolo, "error": str(e)}

def analizar_fundamental_completo() -> dict:
    todos = []
    for simbolo in ACTIVOS:
        print(f"[agente_fundamental] Analizando {simbolo}...")
        datos = obtener_fundamentales(simbolo)
        todos.append(datos)

    resumen = []
    for f in todos:
        if "error" not in f:
            upside = None
            if f.get("precio_objetivo") and f.get("precio_actual"):
                upside = round(((f["precio_objetivo"] / f["precio_actual"]) - 1) * 100, 1)
            resumen.append(
                f"{f['simbolo']}: PE={f.get('pe_ratio','N/A')} | "
                f"PE_fwd={f.get('pe_forward','N/A')} | "
                f"margen={f.get('margen_beneficio','N/A')} | "
                f"deuda={f.get('deuda_equity','N/A')} | "
                f"crec={f.get('crecimiento_earnings','N/A')} | "
                f"recom={f.get('recomendacion_analistas','N/A')} | "
                f"upside={upside}%"
            )

    resumen_texto = "\n".join(resumen)

    print("[agente_fundamental] Analizando con Ollama...")
    respuesta = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "system",
                "content": "Eres un analista fundamental experto. Analiza los datos y entrega: 1) Top 3 empresas infravaloradas 2) Mejor salud financiera 3) Mayor crecimiento 4) Sobrevaloradas 5) Recomendacion comprar/mantener/evitar. Responde en español conciso."
            },
            {
                "role": "user",
                "content": "DATOS FUNDAMENTALES:\n" + resumen_texto
            }
        ]
    )

    return {
        "fundamentales": todos,
        "analisis": respuesta["message"]["content"],
        "modelo": "llama3.2"
    }

def obtener_reporte_fundamental() -> str:
    resultado = analizar_fundamental_completo()
    return resultado.get("analisis", "Sin analisis fundamental")