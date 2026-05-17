# agente_financiero/agente_aprendizaje.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import json
import numpy as np
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

PESOS_FILE = os.path.join(os.path.dirname(__file__), '..', 'logs', 'pesos_agentes.json')
os.makedirs(os.path.dirname(PESOS_FILE), exist_ok=True)

# Pesos iniciales de cada fuente de señal
PESOS_DEFAULT = {
    "velas":      1.0,
    "indicadores":1.0,
    "orderflow":  1.0,
    "niveles":    1.0,
    "onchain":    1.0,
    "funding":    1.0,
    "liquidaciones":1.0,
    "estructura": 1.0,
    "volume_profile":1.0,
    "orb":        1.0,
    "petroleo":   0.5,
    "sentimiento":0.8,
    "macro":      0.8,
    "fundamental":0.7,
    "youtube":    0.5,
}

def cargar_pesos() -> dict:
    try:
        if os.path.exists(PESOS_FILE):
            with open(PESOS_FILE, "r") as f:
                return json.load(f)
        return PESOS_DEFAULT.copy()
    except:
        return PESOS_DEFAULT.copy()

def guardar_pesos(pesos: dict):
    with open(PESOS_FILE, "w") as f:
        json.dump(pesos, f, indent=2)

def obtener_historial_señales() -> list:
    try:
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
        r  = sb.table("señales_trading").select("*").order("timestamp", desc=True).limit(200).execute()
        return r.data
    except Exception as e:
        print(f"[aprendizaje] Error Supabase: {e}")
        return []

def obtener_historial_cierres() -> list:
    try:
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
        r  = sb.table("cierres_trading").select("*").order("timestamp", desc=True).limit(200).execute()
        return r.data
    except Exception as e:
        print(f"[aprendizaje] Error Supabase cierres: {e}")
        return []

def analizar_rendimiento_por_fuente(señales: list, cierres: list) -> dict:
    if not señales or not cierres:
        return {}

    rendimiento = {}
    for cierre in cierres:
        simbolo  = cierre.get("simbolo", "")
        pnl      = cierre.get("pnl_usd", 0)
        resultado = cierre.get("resultado", "")
        ts_cierre = cierre.get("timestamp", "")

        # Busca la señal correspondiente
        señal_match = None
        for s in señales:
            if s.get("simbolo") == simbolo:
                señal_match = s
                break

        if not señal_match:
            continue

        fuentes_str = señal_match.get("fuentes", "")
        fuentes = [f.strip() for f in fuentes_str.split(",") if f.strip()]

        for fuente in fuentes:
            if fuente not in rendimiento:
                rendimiento[fuente] = {
                    "total":    0,
                    "ganancia": 0,
                    "perdida":  0,
                    "pnl_total":0.0,
                }
            rendimiento[fuente]["total"]     += 1
            rendimiento[fuente]["pnl_total"] += float(pnl) if pnl else 0
            if resultado == "GANANCIA":
                rendimiento[fuente]["ganancia"] += 1
            else:
                rendimiento[fuente]["perdida"]  += 1

    # Calcula win rate por fuente
    for fuente in rendimiento:
        total = rendimiento[fuente]["total"]
        if total > 0:
            rendimiento[fuente]["win_rate"] = round(
                rendimiento[fuente]["ganancia"] / total * 100, 1
            )
        else:
            rendimiento[fuente]["win_rate"] = 50.0

    return rendimiento

def ajustar_pesos(rendimiento: dict) -> dict:
    pesos = cargar_pesos()

    for fuente, stats in rendimiento.items():
        if fuente not in pesos:
            continue

        win_rate = stats.get("win_rate", 50)
        total    = stats.get("total", 0)
        pnl      = stats.get("pnl_total", 0)

        if total < 5:
            continue  # Necesita al menos 5 operaciones para ajustar

        # Ajuste basado en win rate
        if win_rate >= 70:
            nuevo_peso = min(pesos[fuente] * 1.2, 3.0)  # Aumenta hasta 3x
        elif win_rate >= 55:
            nuevo_peso = min(pesos[fuente] * 1.05, 3.0)
        elif win_rate < 40:
            nuevo_peso = max(pesos[fuente] * 0.8, 0.1)  # Reduce hasta 0.1x
        elif win_rate < 30:
            nuevo_peso = max(pesos[fuente] * 0.5, 0.1)
        else:
            nuevo_peso = pesos[fuente]  # Sin cambio

        pesos[fuente] = round(nuevo_peso, 3)
        print(f"[aprendizaje] {fuente}: win_rate={win_rate}% → peso={nuevo_peso}")

    guardar_pesos(pesos)
    return pesos

def generar_reporte_aprendizaje() -> dict:
    print("[aprendizaje] Cargando historial de señales...")
    señales = obtener_historial_señales()

    print("[aprendizaje] Cargando historial de cierres...")
    cierres = obtener_historial_cierres()

    print(f"[aprendizaje] Señales: {len(señales)} | Cierres: {len(cierres)}")

    rendimiento = analizar_rendimiento_por_fuente(señales, cierres)
    pesos_actualizados = ajustar_pesos(rendimiento)

    # Ranking de fuentes por efectividad
    ranking = sorted(
        [(f, s.get("win_rate", 50), s.get("pnl_total", 0), s.get("total", 0))
         for f, s in rendimiento.items()],
        key=lambda x: (x[1], x[2]),
        reverse=True
    )

    reporte = {
        "timestamp":          datetime.now().isoformat(),
        "total_señales":      len(señales),
        "total_cierres":      len(cierres),
        "rendimiento":        rendimiento,
        "pesos_actualizados": pesos_actualizados,
        "ranking_fuentes":    ranking,
    }

    print("\n=== RANKING DE FUENTES POR EFECTIVIDAD ===")
    for fuente, win_rate, pnl, total in ranking[:10]:
        print(f"{fuente}: win_rate={win_rate}% | PnL=${round(pnl,2)} | ops={total} | peso={pesos_actualizados.get(fuente,'N/A')}")

    return reporte