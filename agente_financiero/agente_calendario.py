# agente_financiero/agente_calendario.py
import requests
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime, timedelta
from dotenv import load_dotenv
from firecrawl import FirecrawlApp

load_dotenv()

# Eventos de alto impacto que mueven mercados
EVENTOS_ALTO_IMPACTO = [
    "CPI", "Consumer Price Index",
    "FOMC", "Federal Reserve",
    "NFP", "Non-Farm Payroll",
    "GDP", "Gross Domestic Product",
    "PPI", "Producer Price Index",
    "PCE", "Personal Consumption",
    "Unemployment", "Jobs Report",
    "Interest Rate Decision",
    "Earnings", "Apple earnings", "NVDA earnings",
    "Microsoft earnings", "Google earnings",
]

MINUTOS_PAUSA_ANTES = 30  # Pausa 30 min antes del evento
MINUTOS_PAUSA_DESPUES = 30  # Pausa 30 min despues del evento

def obtener_eventos_hoy() -> list:
    try:
        app = FirecrawlApp(api_key=os.getenv("FIRECRAWL_API_KEY"))
        r   = app.scrape(
            "https://www.forexfactory.com/calendar",
            formats=["markdown"]
        )
        texto = r.markdown[:3000]

        # Busca eventos de alto impacto en el texto
        eventos = []
        lineas  = texto.split("\n")
        for linea in lineas:
            for evento in EVENTOS_ALTO_IMPACTO:
                if evento.lower() in linea.lower():
                    eventos.append({
                        "nombre":  evento,
                        "linea":   linea.strip()[:100],
                        "impacto": "ALTO",
                    })
                    break

        return eventos[:10]
    except Exception as e:
        return obtener_eventos_alternativos()

def obtener_eventos_alternativos() -> list:
    try:
        from newsapi import NewsApiClient
        cliente = NewsApiClient(api_key=os.getenv("NEWS_API_KEY"))
        r = cliente.get_everything(
            q="Federal Reserve FOMC CPI NFP earnings today",
            language="en",
            sort_by="publishedAt",
            page_size=5
        )
        eventos = []
        for a in r.get("articles", []):
            titulo = a.get("title", "")
            for evento in EVENTOS_ALTO_IMPACTO:
                if evento.lower() in titulo.lower():
                    eventos.append({
                        "nombre":  evento,
                        "linea":   titulo[:100],
                        "impacto": "ALTO",
                        "fuente":  a.get("source", {}).get("name", ""),
                    })
                    break
        return eventos[:5]
    except Exception as e:
        return []

def debe_pausar_trading() -> dict:
    ahora = datetime.now()
    hora  = ahora.strftime("%H:%M")

    # Horarios conocidos de eventos fijos
    EVENTOS_FIJOS = {
        "08:30": "NFP/CPI/PPI — dato economico USA importante",
        "14:00": "FOMC Decision — decision de tasas Fed",
        "14:30": "Fed Press Conference — conferencia prensa Fed",
        "09:30": "Apertura mercado USA — alta volatilidad primeros 5 min",
        "16:00": "Cierre mercado USA — posible volatilidad",
    }

    # Verifica si estamos cerca de un evento fijo
    for hora_evento, descripcion in EVENTOS_FIJOS.items():
        h_ev = datetime.strptime(hora_evento, "%H:%M").replace(
            year=ahora.year, month=ahora.month, day=ahora.day
        )
        diferencia_min = abs((ahora - h_ev).total_seconds() / 60)

        if diferencia_min <= MINUTOS_PAUSA_ANTES:
            return {
                "pausar":      True,
                "razon":       f"Evento próximo en {round(diferencia_min)}min: {descripcion}",
                "evento":      descripcion,
                "minutos":     round(diferencia_min),
                "tipo":        "EVENTO_FIJO",
            }

    # Busca eventos dinámicos del día
    eventos_hoy = obtener_eventos_hoy()
    if eventos_hoy:
        return {
            "pausar":        False,
            "eventos_hoy":   eventos_hoy,
            "alerta":        f"Hay {len(eventos_hoy)} eventos de alto impacto hoy — operar con precaucion",
            "tipo":          "ALERTA_EVENTOS",
        }

    return {
        "pausar":      False,
        "eventos_hoy": [],
        "razon":       "Sin eventos de alto impacto detectados",
        "tipo":        "LIBRE",
    }

def obtener_proximos_eventos() -> list:
    eventos = []
    ahora   = datetime.now()

    # Eventos recurrentes conocidos
    RECURRENTES = [
        {"nombre": "CPI USA",         "dia_mes": 10, "hora": "08:30", "impacto": "MUY_ALTO"},
        {"nombre": "NFP",             "primer_viernes": True, "hora": "08:30", "impacto": "MUY_ALTO"},
        {"nombre": "FOMC",            "cada_6_semanas": True, "hora": "14:00", "impacto": "MUY_ALTO"},
        {"nombre": "PCE",             "dia_mes": 28, "hora": "08:30", "impacto": "ALTO"},
        {"nombre": "GDP",             "dia_mes": 30, "hora": "08:30", "impacto": "ALTO"},
    ]

    for evento in RECURRENTES:
        eventos.append({
            "nombre":  evento["nombre"],
            "impacto": evento["impacto"],
            "hora":    evento.get("hora", "N/A"),
        })

    return eventos

def analizar_calendario() -> dict:
    print("[agente_calendario] Verificando calendario economico...")
    pausa    = debe_pausar_trading()
    proximos = obtener_proximos_eventos()

    return {
        "debe_pausar":    pausa["pausar"],
        "razon_pausa":    pausa.get("razon", ""),
        "tipo":           pausa.get("tipo", "LIBRE"),
        "eventos_hoy":    pausa.get("eventos_hoy", []),
        "alerta":         pausa.get("alerta", ""),
        "proximos":       proximos,
        "timestamp":      datetime.now().strftime("%H:%M:%S"),
    }