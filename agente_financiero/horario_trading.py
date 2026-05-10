# agente_financiero/horario_trading.py
from datetime import datetime
import pytz

# Sesiones de mercado en UTC
SESIONES = {
    "asia":   {"inicio": 0,  "fin": 8,  "activos": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],        "calidad": "media"},
    "europa": {"inicio": 7,  "fin": 16, "activos": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],        "calidad": "alta"},
    "usa":    {"inicio": 13, "fin": 22, "activos": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"], "calidad": "alta"},
    "overlap":{"inicio": 13, "fin": 16, "activos": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"], "calidad": "muy_alta"},
}

# Horas de alta volatilidad — mejores para trading
HORAS_OPTIMAS = [8, 9, 13, 14, 15, 16, 20, 21]

# Horas a evitar — baja liquidez
HORAS_EVITAR = [0, 1, 2, 3, 4, 5, 6]

def obtener_sesion_actual() -> dict:
    utc  = pytz.UTC
    hora = datetime.now(utc).hour
    minuto = datetime.now(utc).minute

    sesiones_activas = []
    for nombre, sesion in SESIONES.items():
        if sesion["inicio"] <= hora < sesion["fin"]:
            sesiones_activas.append({
                "nombre":   nombre,
                "calidad":  sesion["calidad"],
                "activos":  sesion["activos"],
                "minutos_restantes": (sesion["fin"] - hora) * 60 - minuto,
            })

    # Overlap es la mejor sesion
    es_overlap = hora >= 13 and hora < 16
    es_optima  = hora in HORAS_OPTIMAS
    es_evitar  = hora in HORAS_EVITAR

    if es_evitar:
        recomendacion = "EVITAR — baja liquidez"
        score = 1
    elif es_overlap:
        recomendacion = "EXCELENTE — overlap Europa/USA"
        score = 10
    elif es_optima:
        recomendacion = "BUENA — hora de alta actividad"
        score = 7
    elif sesiones_activas:
        recomendacion = "ACEPTABLE — sesion activa"
        score = 5
    else:
        recomendacion = "BAJA — poca actividad"
        score = 3

    return {
        "hora_utc":        hora,
        "minuto_utc":      minuto,
        "sesiones_activas": sesiones_activas,
        "es_overlap":      es_overlap,
        "es_optima":       es_optima,
        "es_evitar":       es_evitar,
        "recomendacion":   recomendacion,
        "score_sesion":    score,
        "activos_recomendados": sesiones_activas[0]["activos"] if sesiones_activas else ["BTCUSDT", "ETHUSDT"],
    }

def debe_operar() -> dict:
    sesion = obtener_sesion_actual()
    hora   = sesion["hora_utc"]

    # No opera en horas de muy baja liquidez
    if sesion["es_evitar"]:
        return {
            "operar":    False,
            "razon":     f"Hora {hora}:00 UTC — baja liquidez, esperar sesion Asia (8:00 UTC)",
            "score":     sesion["score_sesion"],
            "sesion":    sesion,
        }

    # Opera en cualquier otra hora pero con diferente agresividad
    if sesion["score_sesion"] >= 7:
        agresividad = "ALTA"
        max_operaciones = 2
    elif sesion["score_sesion"] >= 5:
        agresividad = "MEDIA"
        max_operaciones = 1
    else:
        agresividad = "BAJA"
        max_operaciones = 1

    return {
        "operar":           True,
        "agresividad":      agresividad,
        "max_operaciones":  max_operaciones,
        "razon":            sesion["recomendacion"],
        "score":            sesion["score_sesion"],
        "sesion":           sesion,
    }

def proxima_sesion_optima() -> str:
    utc  = pytz.UTC
    hora = datetime.now(utc).hour
    for h in HORAS_OPTIMAS:
        if h > hora:
            return f"{h}:00 UTC"
    return f"{HORAS_OPTIMAS[0]}:00 UTC (mañana)"