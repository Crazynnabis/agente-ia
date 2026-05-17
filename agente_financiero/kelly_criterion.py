# agente_financiero/kelly_criterion.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import json
import numpy as np
from datetime import datetime, timedelta
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

KELLY_FILE = os.path.join(os.path.dirname(__file__), '..', 'logs', 'kelly_params.json')
os.makedirs(os.path.dirname(KELLY_FILE), exist_ok=True)

# Configuracion de seguridad
KELLY_FRACCION    = 0.25   # Usa 25% del Kelly completo — mas conservador
KELLY_MIN         = 0.005  # Minimo 0.5% del capital
KELLY_MAX         = 0.02   # Maximo 2% del capital
CAPITAL_BASE      = 100000 # Capital paper trading

# Parametros por defecto hasta tener datos reales
DEFAULTS = {
    "win_rate":     0.40,   # 40% win rate estimado
    "avg_win":      0.015,  # 1.5% ganancia promedio
    "avg_loss":     0.008,  # 0.8% perdida promedio
    "total_trades": 0,
}

def cargar_parametros_kelly() -> dict:
    try:
        if os.path.exists(KELLY_FILE):
            with open(KELLY_FILE, "r") as f:
                return json.load(f)
        return DEFAULTS.copy()
    except:
        return DEFAULTS.copy()

def guardar_parametros_kelly(params: dict):
    with open(KELLY_FILE, "w") as f:
        json.dump(params, f, indent=2)

def calcular_kelly(win_rate: float, avg_win: float, avg_loss: float) -> float:
    if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
        return KELLY_MIN

    # Formula Kelly: f = (p*b - q) / b
    # p = probabilidad de ganar
    # q = probabilidad de perder = 1-p
    # b = ratio ganancia/perdida
    p = win_rate
    q = 1 - win_rate
    b = avg_win / avg_loss if avg_loss > 0 else 1.0

    kelly_completo = (p * b - q) / b

    # Aplica fraccion de Kelly para seguridad
    kelly_fraccionado = kelly_completo * KELLY_FRACCION

    # Limita entre min y max
    kelly_final = max(KELLY_MIN, min(KELLY_MAX, kelly_fraccionado))

    return round(kelly_final, 4)

def obtener_estadisticas_reales() -> dict:
    try:
        sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

        # Obtiene cierres reales de Supabase
        r = sb.table("cierres_trading").select("*").order(
            "timestamp", desc=True
        ).limit(100).execute()

        cierres = r.data
        if not cierres or len(cierres) < 5:
            print("[kelly] Sin suficientes datos reales — usando defaults")
            return DEFAULTS.copy()

        ganancias = [c["pnl_pct"] for c in cierres if c.get("pnl_usd", 0) > 0]
        perdidas  = [abs(c["pnl_pct"]) for c in cierres if c.get("pnl_usd", 0) < 0]

        total     = len(cierres)
        wins      = len(ganancias)
        win_rate  = wins / total if total > 0 else DEFAULTS["win_rate"]
        avg_win   = np.mean(ganancias) / 100 if ganancias else DEFAULTS["avg_win"]
        avg_loss  = np.mean(perdidas)  / 100 if perdidas  else DEFAULTS["avg_loss"]

        return {
            "win_rate":     round(win_rate, 4),
            "avg_win":      round(avg_win, 4),
            "avg_loss":     round(avg_loss, 4),
            "total_trades": total,
        }
    except Exception as e:
        print(f"[kelly] Error Supabase: {e}")
        return DEFAULTS.copy()

def calcular_tamaño_kelly(precio: float, stop_loss: float,
                          estrategia: str = "general") -> dict:
    params = obtener_estadisticas_reales()

    win_rate = params["win_rate"]
    avg_win  = params["avg_win"]
    avg_loss = params["avg_loss"]

    # Kelly por estrategia si hay suficientes datos
    kelly_pct = calcular_kelly(win_rate, avg_win, avg_loss)

    capital       = CAPITAL_BASE
    riesgo_usd    = capital * kelly_pct
    distancia_sl  = abs(precio - stop_loss)

    if distancia_sl == 0:
        return {"error": "Stop loss igual al precio"}

    cantidad = riesgo_usd / distancia_sl

    # Limite maximo de posicion 20% del capital
    valor_posicion = cantidad * precio
    if valor_posicion > capital * 0.20:
        cantidad       = (capital * 0.20) / precio
        valor_posicion = capital * 0.20

    return {
        "kelly_pct":         round(kelly_pct * 100, 3),
        "riesgo_usd":        round(riesgo_usd, 2),
        "cantidad":          round(cantidad, 6),
        "valor_posicion":    round(valor_posicion, 2),
        "win_rate_usado":    round(win_rate * 100, 1),
        "avg_win_usado":     round(avg_win * 100, 3),
        "avg_loss_usado":    round(avg_loss * 100, 3),
        "total_trades_base": params["total_trades"],
        "fuente":            "real" if params["total_trades"] >= 5 else "default",
    }

def actualizar_parametros_kelly():
    print("[kelly] Actualizando parametros con datos reales...")
    params = obtener_estadisticas_reales()
    guardar_parametros_kelly(params)

    kelly = calcular_kelly(
        params["win_rate"],
        params["avg_win"],
        params["avg_loss"]
    )

    print(f"[kelly] Win rate: {round(params['win_rate']*100,1)}%")
    print(f"[kelly] Avg win: {round(params['avg_win']*100,3)}%")
    print(f"[kelly] Avg loss: {round(params['avg_loss']*100,3)}%")
    print(f"[kelly] Kelly optimo: {round(kelly*100,3)}% del capital por operacion")
    print(f"[kelly] Trades analizados: {params['total_trades']}")

    return {
        "kelly_pct":    round(kelly * 100, 3),
        "parametros":   params,
    }