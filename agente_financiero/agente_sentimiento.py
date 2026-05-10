# agente_financiero/agente_sentimiento.py
import requests
import ollama
from firecrawl import FirecrawlApp
import os
from dotenv import load_dotenv

load_dotenv()

def obtener_fear_greed() -> dict:
    try:
        r = requests.get("https://api.alternative.me/fng/?limit=7", timeout=10)
        data = r.json()["data"]
        hoy = data[0]
        semana = [d for d in data]
        promedio = sum(int(d["value"]) for d in semana) // len(semana)
        return {
            "valor_hoy": int(hoy["value"]),
            "clasificacion": hoy["value_classification"],
            "promedio_7dias": promedio,
            "tendencia": "mejorando" if int(data[0]["value"]) > int(data[-1]["value"]) else "empeorando"
        }
    except Exception as e:
        return {"error": str(e)}

def obtener_sentimiento_reddit() -> str:
    try:
        app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
        resultado = app.scrape("https://www.reddit.com/r/investing/hot/.json", formats=["markdown"])
        return resultado.markdown[:2000]
    except Exception as e:
        return f"Error Reddit: {e}"

def obtener_sentimiento_crypto() -> str:
    try:
        app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
        resultado = app.scrape("https://coinmarketcap.com/trending-cryptocurrencies/", formats=["markdown"])
        return resultado.markdown[:2000]
    except Exception as e:
        return f"Error crypto: {e}"

def analizar_sentimiento_mercado() -> dict:
    print("[agente_sentimiento] Obteniendo Fear & Greed Index...")
    fg = obtener_fear_greed()
    
    print("[agente_sentimiento] Scrapeando Reddit investing...")
    reddit = obtener_sentimiento_reddit()
    
    print("[agente_sentimiento] Scrapeando crypto trending...")
    crypto = obtener_sentimiento_crypto()
    
    contexto = f"""
Fear & Greed Index hoy: {fg.get('valor_hoy', 'N/A')} ({fg.get('clasificacion', 'N/A')})
Promedio 7 días: {fg.get('promedio_7dias', 'N/A')}
Tendencia: {fg.get('tendencia', 'N/A')}

Reddit r/investing (posts calientes):
{reddit[:1000]}

Crypto trending:
{crypto[:1000]}
"""
    
    print("[agente_sentimiento] Analizando con Ollama...")
    respuesta = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "system",
                "content": """Eres un analista de sentimiento de mercado experto.
Analiza los datos y entrega un reporte con:
1. Sentimiento general del mercado (muy bajista/bajista/neutral/alcista/muy alcista)
2. Nivel de miedo o codicia predominante
3. Activos con mayor momentum positivo
4. Activos con mayor momentum negativo  
5. Recomendación: ¿Es buen momento para comprar, mantener o vender?
6. Señales de alerta detectadas
Responde en español, de forma concisa y estructurada."""
            },
            {
                "role": "user",
                "content": f"Analiza este sentimiento de mercado:\n{contexto}"
            }
        ]
    )
    
    return {
        "fear_greed": fg,
        "analisis": respuesta["message"]["content"],
        "modelo": "llama3.2"
    }

def obtener_reporte_sentimiento() -> str:
    resultado = analizar_sentimiento_mercado()
    fg = resultado.get("fear_greed", {})
    header = f"Fear & Greed: {fg.get('valor_hoy', 'N/A')} — {fg.get('clasificacion', 'N/A')}"
    return f"{header}\n\n{resultado.get('analisis', 'Sin análisis')}"