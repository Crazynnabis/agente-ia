# agente_financiero/agente_news_momentum.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import requests
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv
from newsapi import NewsApiClient

load_dotenv()

EMPRESAS_SEGUIMIENTO = {
    "AAPL":  ["Apple", "iPhone", "Tim Cook", "Apple earnings"],
    "NVDA":  ["Nvidia", "Jensen Huang", "GPU", "AI chips", "CUDA"],
    "MSFT":  ["Microsoft", "Satya Nadella", "Azure", "OpenAI"],
    "TSLA":  ["Tesla", "Elon Musk", "EV", "electric vehicle"],
    "AMZN":  ["Amazon", "AWS", "Jeff Bezos", "Andy Jassy"],
    "GOOGL": ["Google", "Alphabet", "Sundar Pichai", "Gemini AI"],
    "META":  ["Meta", "Facebook", "Mark Zuckerberg", "Instagram"],
    "BTC":   ["Bitcoin", "BTC", "crypto regulation", "SEC Bitcoin"],
    "ETH":   ["Ethereum", "ETH", "Vitalik", "Ethereum ETF"],
}

PALABRAS_ALCISTAS = [
    "beat", "record", "surge", "rally", "profit", "growth",
    "upgrade", "buy", "bullish", "breakthrough", "approved",
    "partnership", "acquisition", "dividend", "buyback",
    "supera", "record", "ganancias", "crecimiento", "aprobado"
]

PALABRAS_BAJISTAS = [
    "miss", "loss", "crash", "decline", "downgrade", "sell",
    "bearish", "lawsuit", "fine", "recall", "bankruptcy",
    "layoff", "scandal", "investigation", "hack", "breach",
    "pierde", "caida", "perdida", "demanda", "multa", "fraude"
]

def obtener_noticias_empresa(simbolo: str, keywords: list) -> list:
    try:
        cliente = NewsApiClient(api_key=os.getenv("NEWS_API_KEY"))
        query   = " OR ".join(keywords[:3])
        r = cliente.get_everything(
            q=query,
            language="en",
            sort_by="publishedAt",
            from_param=(datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S"),
            page_size=10
        )
        return r.get("articles", [])
    except Exception as e:
        return []

def calcular_score_sentimiento(articulos: list) -> dict:
    score_total  = 0
    score_detalle = []

    for articulo in articulos:
        titulo      = (articulo.get("title", "") or "").lower()
        descripcion = (articulo.get("description", "") or "").lower()
        texto       = titulo + " " + descripcion

        score_art = 0
        for palabra in PALABRAS_ALCISTAS:
            if palabra in texto:
                score_art += 1
        for palabra in PALABRAS_BAJISTAS:
            if palabra in texto:
                score_art -= 1

        score_total += score_art
        if abs(score_art) > 0:
            score_detalle.append({
                "titulo": articulo.get("title", "")[:80],
                "score":  score_art,
                "fuente": articulo.get("source", {}).get("name", ""),
            })

    return {
        "score_total":  score_total,
        "articulos":    len(articulos),
        "detalle":      score_detalle[:5],
    }

def obtener_movimiento_precio(simbolo: str) -> dict:
    try:
        simbolo_yf = simbolo if not simbolo.endswith("USDT") else simbolo.replace("USDT", "-USD")
        ticker = yf.Ticker(simbolo_yf)
        df     = ticker.history(period="2d", interval="1h")
        if df.empty:
            return {}

        precio_actual = float(df["Close"].iloc[-1])
        precio_6h     = float(df["Close"].iloc[-7]) if len(df) > 7 else precio_actual
        precio_24h    = float(df["Close"].iloc[-25]) if len(df) > 25 else precio_actual
        volumen_hoy   = float(df["Volume"].tail(8).sum())
        volumen_prom  = float(df["Volume"].mean() * 8)

        return {
            "precio":        round(precio_actual, 4),
            "cambio_6h":     round(((precio_actual - precio_6h) / precio_6h) * 100, 3),
            "cambio_24h":    round(((precio_actual - precio_24h) / precio_24h) * 100, 3),
            "ratio_volumen": round(volumen_hoy / volumen_prom, 2) if volumen_prom > 0 else 1.0,
        }
    except:
        return {}

def analizar_news_momentum(simbolo: str) -> dict:
    keywords = EMPRESAS_SEGUIMIENTO.get(simbolo, [simbolo])

    print(f"[agente_news] Buscando noticias de {simbolo}...")
    articulos = obtener_noticias_empresa(simbolo, keywords)
    sentimiento = calcular_score_sentimiento(articulos)
    precio_mov  = obtener_movimiento_precio(simbolo)

    score = sentimiento["score_total"]

    # Confirma con movimiento de precio
    cambio_6h = precio_mov.get("cambio_6h", 0)
    ratio_vol  = precio_mov.get("ratio_volumen", 1.0)

    # Señal de momentum
    señal  = "ESPERAR"
    fuerza = "baja"

    if score >= 3 and cambio_6h > 0.5 and ratio_vol > 1.3:
        señal  = "COMPRAR"
        fuerza = "muy_alta"
    elif score >= 2 and cambio_6h > 0:
        señal  = "COMPRAR"
        fuerza = "alta"
    elif score >= 1:
        señal  = "COMPRAR"
        fuerza = "media"
    elif score <= -3 and cambio_6h < -0.5 and ratio_vol > 1.3:
        señal  = "VENDER"
        fuerza = "muy_alta"
    elif score <= -2 and cambio_6h < 0:
        señal  = "VENDER"
        fuerza = "alta"
    elif score <= -1:
        señal  = "VENDER"
        fuerza = "media"

    precio = precio_mov.get("precio", 0)

    return {
        "simbolo":       simbolo,
        "precio":        precio,
        "score_noticias": score,
        "articulos":     sentimiento["articulos"],
        "noticias_clave": sentimiento["detalle"][:3],
        "cambio_6h":     precio_mov.get("cambio_6h", 0),
        "cambio_24h":    precio_mov.get("cambio_24h", 0),
        "ratio_volumen": ratio_vol,
        "señal":         señal,
        "fuerza":        fuerza,
        "timestamp":     datetime.now().strftime("%H:%M:%S"),
    }

def ejecutar_news_momentum() -> list:
    resultados = []
    for simbolo in EMPRESAS_SEGUIMIENTO.keys():
        r = analizar_news_momentum(simbolo)
        resultados.append(r)
    return resultados

def obtener_reporte_news_momentum() -> str:
    resultados = ejecutar_news_momentum()
    lineas = []
    for r in resultados:
        if r.get("señal") != "ESPERAR":
            lineas.append(
                f"{r['simbolo']}: {r['señal']} ({r['fuerza']}) | "
                f"score={r['score_noticias']} | "
                f"6h={r['cambio_6h']}% | vol={r['ratio_volumen']}x"
            )
    return "\n".join(lineas) if lineas else "Sin momentum de noticias detectado"