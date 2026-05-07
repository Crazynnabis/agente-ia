import os
from firecrawl import FirecrawlApp
from dotenv import load_dotenv

load_dotenv()

FUENTES = [
    "https://finance.yahoo.com",
    "https://www.marketwatch.com",
]

def obtener_noticias_mercado(max_chars: int = 3000) -> str:
    api_key = os.getenv("FIRECRAWL_API_KEY")
    if not api_key:
        return "Firecrawl no configurado"
    app = FirecrawlApp(api_key=api_key)
    noticias = []
    for url in FUENTES:
        try:
            resultado = app.scrape(url, formats=["markdown"])
            noticias.append(f"=== {url} ===\n{resultado.markdown[:1000]}")
        except Exception as e:
            print(f"[noticias_web] Error: {e}")
    return "\n\n".join(noticias)[:max_chars]