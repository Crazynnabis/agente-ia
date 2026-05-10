# agente_financiero/agente_macro.py
import os
import requests
import ollama
from firecrawl import FirecrawlApp
from dotenv import load_dotenv

load_dotenv()

FUENTES_MACRO = {
    "fed": "https://www.federalreserve.gov/newsevents/pressreleases.htm",
    "geopolitica": "https://www.bbc.com/news/world",
    "economia_mx": "https://www.eleconomista.com.mx/mercados",
    "white_house": "https://www.whitehouse.gov/news/",
    "banxico": "https://www.banxico.org.mx/publicaciones-y-prensa/anuncios-de-las-decisiones-de-politica-monetaria",
}

FUENTES_NOTICIAS = [
    "geopolitics economy market",
    "federal reserve interest rates",
    "inflation recession GDP",
    "oil price OPEC",
    "china economy trade",
    "election president policy economy",
]

def obtener_noticias_macro() -> str:
    from newsapi import NewsApiClient
    try:
        cliente = NewsApiClient(api_key=os.getenv("NEWS_API_KEY"))
        todas = []
        for query in FUENTES_NOTICIAS[:3]:
            r = cliente.get_everything(
                q=query,
                language="en",
                sort_by="publishedAt",
                page_size=3
            )
            for a in r.get("articles", []):
                todas.append(f"- {a['title']} ({a['source']['name']})")
        return "\n".join(todas[:15])
    except Exception as e:
        return f"Error NewsAPI: {e}"

def obtener_noticias_web() -> str:
    try:
        app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
        resultado = app.scrape(FUENTES_MACRO["geopolitica"], formats=["markdown"])
        return resultado.markdown[:2000]
    except Exception as e:
        return f"Error web: {e}"

def analizar_contexto_macro() -> dict:
    print("[agente_macro] Obteniendo noticias macro con NewsAPI...")
    noticias = obtener_noticias_macro()

    print("[agente_macro] Scrapeando BBC geopolítica...")
    web = obtener_noticias_web()

    contexto = f"""
NOTICIAS MACROECONÓMICAS Y GEOPOLÍTICAS:
{noticias}

NOTICIAS GLOBALES (BBC):
{web[:1500]}
"""

    print("[agente_macro] Analizando impacto en mercados con Ollama...")
    respuesta = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "system",
                "content": """Eres un analista macroeconómico y geopolítico experto en mercados financieros.
Analiza las noticias y entrega un reporte con:
1. Eventos geopolíticos con impacto en mercados (guerras, elecciones, sanciones)
2. Decisiones de bancos centrales (FED, BCE, Banxico) y su impacto
3. Indicadores económicos relevantes (inflación, PIB, empleo)
4. Sectores favorecidos por el contexto actual
5. Sectores perjudicados por el contexto actual
6. Nivel de riesgo geopolítico: BAJO / MEDIO / ALTO
7. Impacto esperado en mercados: alcista / bajista / neutral
Responde en español, conciso y estructurado."""
            },
            {
                "role": "user",
                "content": f"Analiza este contexto macroeconómico:\n{contexto}"
            }
        ]
    )

    return {
        "noticias_count": len(noticias.split("\n")),
        "analisis": respuesta["message"]["content"],
        "modelo": "llama3.2"
    }

def obtener_reporte_macro() -> str:
    resultado = analizar_contexto_macro()
    return resultado.get("analisis", "Sin análisis macro disponible")