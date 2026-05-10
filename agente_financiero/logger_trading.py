# agente_financiero/logger_trading.py
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# Log local como respaldo
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"trading_{datetime.now().strftime('%Y%m%d')}.jsonl")

def obtener_supabase():
    try:
        return create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY")
        )
    except:
        return None

def log_señal(simbolo: str, accion: str, precio: float, sl: float,
              tp1: float, tp2: float, confianza: float,
              fuentes: list, razon: str, horizonte: str,
              aprobada_riesgo: bool, aprobada_tendencia: bool,
              tamaño_posicion: dict = None) -> dict:

    registro = {
        "timestamp":           datetime.now().isoformat(),
        "tipo":                "SEÑAL",
        "simbolo":             simbolo,
        "accion":              accion,
        "precio":              precio,
        "stop_loss":           sl,
        "take_profit_1":       tp1,
        "take_profit_2":       tp2,
        "confianza":           confianza,
        "fuentes":             fuentes if isinstance(fuentes, str) else ",".join(fuentes),
        "razon":               razon,
        "horizonte":           horizonte,
        "aprobada_riesgo":     aprobada_riesgo,
        "aprobada_tendencia":  aprobada_tendencia,
        "cantidad":            tamaño_posicion.get("cantidad", 0) if tamaño_posicion else 0,
        "valor_posicion_usd":  tamaño_posicion.get("valor_posicion_usd", 0) if tamaño_posicion else 0,
        "riesgo_usd":          tamaño_posicion.get("riesgo_usd", 0) if tamaño_posicion else 0,
    }

    # Guarda en archivo local
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro) + "\n")

    # Guarda en Supabase
    try:
        sb = obtener_supabase()
        if sb:
            sb.table("señales_trading").insert(registro).execute()
    except Exception as e:
        print(f"[logger] Error Supabase: {e}")

    print(f"[logger] Señal registrada: {accion} {simbolo} @ {precio} | confianza={confianza}%")
    return registro

def log_orden(simbolo: str, accion: str, precio: float,
              cantidad: float, orden_id: str, estado: str) -> dict:

    registro = {
        "timestamp":  datetime.now().isoformat(),
        "tipo":       "ORDEN",
        "simbolo":    simbolo,
        "accion":     accion,
        "precio":     precio,
        "cantidad":   cantidad,
        "orden_id":   orden_id,
        "estado":     estado,
    }

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro) + "\n")

    try:
        sb = obtener_supabase()
        if sb:
            sb.table("ordenes_trading").insert(registro).execute()
    except Exception as e:
        print(f"[logger] Error Supabase orden: {e}")

    print(f"[logger] Orden registrada: {estado} {accion} {simbolo} x{cantidad} @ {precio}")
    return registro

def log_cierre(simbolo: str, precio_entrada: float, precio_cierre: float,
               cantidad: float, pnl_usd: float, razon_cierre: str) -> dict:

    pnl_pct = round(((precio_cierre - precio_entrada) / precio_entrada) * 100, 3)

    registro = {
        "timestamp":      datetime.now().isoformat(),
        "tipo":           "CIERRE",
        "simbolo":        simbolo,
        "precio_entrada": precio_entrada,
        "precio_cierre":  precio_cierre,
        "cantidad":       cantidad,
        "pnl_usd":        round(pnl_usd, 2),
        "pnl_pct":        pnl_pct,
        "razon_cierre":   razon_cierre,
        "resultado":      "GANANCIA" if pnl_usd > 0 else "PERDIDA",
    }

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro) + "\n")

    try:
        sb = obtener_supabase()
        if sb:
            sb.table("cierres_trading").insert(registro).execute()
    except Exception as e:
        print(f"[logger] Error Supabase cierre: {e}")

    emoji = "✓" if pnl_usd > 0 else "✗"
    print(f"[logger] {emoji} Cierre {simbolo}: PnL=${round(pnl_usd,2)} ({pnl_pct}%)")
    return registro

def log_ciclo(ciclo_num: int, señales_detectadas: int,
              ordenes_ejecutadas: int, duracion_segundos: float,
              modelo_usado: str) -> dict:

    registro = {
        "timestamp":          datetime.now().isoformat(),
        "tipo":               "CICLO",
        "ciclo_num":          ciclo_num,
        "señales_detectadas": señales_detectadas,
        "ordenes_ejecutadas": ordenes_ejecutadas,
        "duracion_segundos":  round(duracion_segundos, 1),
        "modelo_usado":       modelo_usado,
    }

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro) + "\n")

    print(f"[logger] Ciclo {ciclo_num}: {señales_detectadas} señales | {ordenes_ejecutadas} ordenes | {round(duracion_segundos,1)}s")
    return registro

def obtener_estadisticas_dia() -> dict:
    if not os.path.exists(LOG_FILE):
        return {"error": "Sin logs hoy"}

    señales  = []
    ordenes  = []
    cierres  = []

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for linea in f:
            try:
                r = json.loads(linea)
                if r["tipo"] == "SEÑAL":  señales.append(r)
                if r["tipo"] == "ORDEN":  ordenes.append(r)
                if r["tipo"] == "CIERRE": cierres.append(r)
            except:
                continue

    ganancias = [c["pnl_usd"] for c in cierres if c["pnl_usd"] > 0]
    perdidas  = [c["pnl_usd"] for c in cierres if c["pnl_usd"] < 0]
    pnl_total = sum(c["pnl_usd"] for c in cierres)
    win_rate  = len(ganancias) / len(cierres) * 100 if cierres else 0

    return {
        "fecha":              datetime.now().strftime("%Y-%m-%d"),
        "total_señales":      len(señales),
        "total_ordenes":      len(ordenes),
        "total_cierres":      len(cierres),
        "ganancias":          len(ganancias),
        "perdidas":           len(perdidas),
        "win_rate":           round(win_rate, 1),
        "pnl_total_usd":      round(pnl_total, 2),
        "ganancia_promedio":  round(sum(ganancias)/len(ganancias), 2) if ganancias else 0,
        "perdida_promedio":   round(sum(perdidas)/len(perdidas), 2) if perdidas else 0,
    }