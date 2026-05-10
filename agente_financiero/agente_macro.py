# agente_financiero/agente_macro.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from firecrawl import FirecrawlApp
from dotenv import load_dotenv
from newsapi import NewsApiClient
from nucleo.cliente_ia import chat

load_dotenv()

FUENTES_NOTICIAS = [
    "federal reserve interest rates",
    "geopolitics economy market",
    "inflation recession GDP",
]

def obtener_noticias_macro() -> str:
    try:
        cliente = NewsApiClient(api_key=os.getenv("NEWS_API_KEY"))
        todas = []
        for query in FUENTES_NOTICIAS:
            r = cliente.get_everything(q=query, language="en", sort_by="publishedAt", page_size=3)
            for a in r.get("articles", []):
                todas.append(f"- {a['title']} ({a['source']['name']})")
        return "\n".join(todas[:15])
    except Exception as e:
        return f"Error NewsAPI: {e}"

def obtener_noticias_web() -> str:
    try:
        app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
        resultado = app.scrape("https://www.bbc.com/news/world", formats=["markdown"])
        return resultado.markdown[:2000]
    except Exception as e:
        return f"Error web: {e}"

async def analizar_contexto_macro() -> dict:
    print("[agente_macro] Obteniendo noticias macro...")
    noticias = obtener_noticias_macro()

    print("[agente_macro] Scrapeando BBC...")
    web = obtener_noticias_web()

    contexto = f"""
NOTICIAS MACROECONÓMICAS:
{noticias}

NOTICIAS GLOBALES (BBC):
{web[:1500]}
"""

    print("[agente_macro] Analizando con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"Analiza este contexto macroeconómico:\n{contexto}"}],
        system="""Eres un analista macroeconómico y geopolítico experto en mercados financieros.
Analiza las noticias y entrega:
1. Eventos geopolíticos con impacto en mercados
2. Decisiones de bancos centrales y su impacto
3. Indicadores económicos relevantes
4. Sectores favorecidos por el contexto actual
5. Sectores perjudicados
6. Nivel de riesgo geopolítico: BAJO / MEDIO / ALTO
7. Impacto esperado en mercados: alcista / bajista / neutral
Responde en español, conciso y estructurado.""",
        max_tokens=800
    )

    return {
        "noticias_count": len(noticias.split("\n")),
        "analisis": respuesta["texto"],
        "modelo": respuesta["modelo"]
    }

async def obtener_reporte_macro() -> str:
    resultado = await analizar_contexto_macro()
    return resultado.get("analisis", "Sin análisis macro")