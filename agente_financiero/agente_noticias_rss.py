# agente_financiero/agente_noticias_rss.py
# Noticias en tiempo real via RSS — CoinDesk, Reuters, CoinTelegraph
# Sin API key, completamente gratis
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import requests
import time
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

# Cache — 15 minutos
_cache_noticias = {}
_cache_ts       = {}
TTL_NOTICIAS    = 900  # 15 minutos

# Feeds RSS gratuitos
RSS_FEEDS = {
    "coindesk":     "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "reuters_biz":  "https://feeds.reuters.com/reuters/businessNews",
    "decrypt":      "https://decrypt.co/feed",
}

# Palabras clave por activo
KEYWORDS_ACTIVOS = {
    "BTCUSDT": ["bitcoin", "btc", "satoshi", "crypto", "cryptocurrency"],
    "ETHUSDT": ["ethereum", "eth", "vitalik", "defi", "smart contract"],
    "SOLUSDT": ["solana", "sol", "anatoly"],
    "BNBUSDT": ["binance", "bnb", "cz", "changpeng"],
}

# Palabras de alto impacto — mueven precio
PALABRAS_ALCISTAS = [
    "surge", "rally", "soars", "jumps", "bull", "adoption",
    "etf", "approved", "partnership", "launch", "upgrade",
    "record", "ath", "institutional", "sube", "alcanza", "rompe",
    "aprobado", "adopción", "récord",
]
PALABRAS_BAJISTAS = [
    "crash", "plunge", "falls", "drops", "ban", "hack", "exploit",
    "sec", "lawsuit", "fraud", "scam", "bear", "collapse", "dump",
    "prohibición", "hackeo", "demanda", "cae", "desplome", "prohíbe",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TradingBot/1.0)"
}

def obtener_noticias_feed(nombre: str, url: str) -> list:
    """Descarga y parsea un feed RSS."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []

        root  = ET.fromstring(r.content)
        items = root.findall(".//item")
        noticias = []

        for item in items[:20]:  # Solo las 20 más recientes
            titulo  = item.findtext("title", "")
            link    = item.findtext("link", "")
            desc    = item.findtext("description", "")
            pubdate = item.findtext("pubDate", "")

            if not titulo:
                continue

            noticias.append({
                "titulo":  titulo.strip(),
                "link":    link.strip(),
                "desc":    desc.strip()[:200],
                "fecha":   pubdate.strip(),
                "fuente":  nombre,
            })

        return noticias
    except Exception as e:
        print(f"[agente_noticias] Error {nombre}: {e}")
        return []

def analizar_impacto(titulo: str, desc: str) -> tuple:
    """
    Analiza el impacto de una noticia.
    Retorna (impacto, señal) donde impacto es 0-10 y señal es COMPRAR/VENDER/NEUTRAL
    """
    texto = (titulo + " " + desc).lower()

    puntos_alcista = sum(1 for p in PALABRAS_ALCISTAS if p in texto)
    puntos_bajista = sum(1 for p in PALABRAS_BAJISTAS if p in texto)

    # Peso extra para palabras muy relevantes
    if any(p in texto for p in ["etf approved", "sec approved", "institutional"]):
        puntos_alcista += 3
    if any(p in texto for p in ["sec lawsuit", "ban", "hack", "exploit", "fraud"]):
        puntos_bajista += 3

    impacto = min((puntos_alcista + puntos_bajista) * 2, 10)

    if puntos_alcista > puntos_bajista:
        señal = "COMPRAR"
    elif puntos_bajista > puntos_alcista:
        señal = "VENDER"
    else:
        señal = "NEUTRAL"

    return impacto, señal

def ejecutar_agente_noticias() -> list:
    """
    Descarga noticias de todos los feeds, filtra por activo
    y calcula impacto. Resultado compatible con el sistema.
    """
    ahora = time.time()

    # Cache global de noticias
    cache_key = "todas"
    if cache_key in _cache_noticias and (ahora - _cache_ts.get(cache_key, 0)) < TTL_NOTICIAS:
        print(f"[agente_noticias] Cache hit — {len(_cache_noticias[cache_key])} noticias")
        return _cache_noticias[cache_key]

    print(f"[agente_noticias] Descargando feeds RSS...")

    # Descarga todos los feeds
    todas_noticias = []
    for nombre, url in RSS_FEEDS.items():
        noticias = obtener_noticias_feed(nombre, url)
        todas_noticias.extend(noticias)
        print(f"[agente_noticias] {nombre}: {len(noticias)} noticias")
        time.sleep(0.5)  # Respetuoso con los servidores

    # Analiza impacto por activo
    resultados = []
    for simbolo, keywords in KEYWORDS_ACTIVOS.items():
        noticias_activo = []

        for noticia in todas_noticias:
            texto = (noticia["titulo"] + " " + noticia["desc"]).lower()
            if any(kw in texto for kw in keywords):
                impacto, señal = analizar_impacto(noticia["titulo"], noticia["desc"])
                noticias_activo.append({
                    **noticia,
                    "impacto": impacto,
                    "señal":   señal,
                })

        # Ordena por impacto
        noticias_activo.sort(key=lambda x: x["impacto"], reverse=True)

        # Calcula señal consolidada del activo
        if noticias_activo:
            compras = sum(1 for n in noticias_activo if n["señal"] == "COMPRAR")
            ventas  = sum(1 for n in noticias_activo if n["señal"] == "VENDER")
            impacto_max = noticias_activo[0]["impacto"]

            if compras > ventas and impacto_max >= 4:
                señal_final = "COMPRAR"
                fuerza      = "alta" if impacto_max >= 6 else "media"
            elif ventas > compras and impacto_max >= 4:
                señal_final = "VENDER"
                fuerza      = "alta" if impacto_max >= 6 else "media"
            else:
                señal_final = "ESPERAR"
                fuerza      = "baja"

            noticia_top = noticias_activo[0]
        else:
            señal_final = "ESPERAR"
            fuerza      = "baja"
            impacto_max = 0
            noticia_top = {}

        resultados.append({
            "simbolo":       simbolo,
            "señal":         señal_final,
            "fuerza":        fuerza,
            "impacto":       impacto_max,
            "num_noticias":  len(noticias_activo),
            "titulo_top":    noticia_top.get("titulo", "Sin noticias relevantes"),
            "fuente_top":    noticia_top.get("fuente", ""),
            "noticias":      noticias_activo[:5],  # Top 5
            "timestamp":     datetime.now().strftime("%H:%M:%S"),
            "error":         False,
        })

        print(f"[agente_noticias] {simbolo}: {len(noticias_activo)} noticias | señal={señal_final}")

    # Guarda en cache
    _cache_noticias[cache_key] = resultados
    _cache_ts[cache_key]       = ahora

    return resultados

def obtener_alertas_criticas() -> list:
    """
    Retorna solo noticias con impacto alto (>=6) para alertas inmediatas.
    Se puede llamar desde el loop_2m para alertas urgentes.
    """
    resultados = ejecutar_agente_noticias()
    return [r for r in resultados if r["impacto"] >= 6 and r["señal"] != "ESPERAR"]