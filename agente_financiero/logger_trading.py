# agente_financiero/logger_trading.py
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from collections import defaultdict
from supabase import create_client
from dotenv import load_dotenv

load_dotenv(r'C:\Users\Oscar Hernandez\.env', override=True)
load_dotenv(override=False)

LOG_DIR  = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, f"trading_{datetime.now().strftime('%Y%m%d')}.jsonl")

# Archivo de aprendizaje — persiste entre sesiones
APRENDIZAJE_FILE = os.path.join(LOG_DIR, "aprendizaje_activos.json")

def obtener_supabase():
    try:
        return create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY")
        )
    except:
        return None

# ============================================================
# SISTEMA DE APRENDIZAJE — persiste entre sesiones
# ============================================================
def cargar_aprendizaje() -> dict:
    """Carga el historial de rendimiento por activo desde disco."""
    try:
        if os.path.exists(APRENDIZAJE_FILE):
            with open(APRENDIZAJE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return {}

def guardar_aprendizaje(datos: dict):
    """Guarda el historial de rendimiento por activo en disco."""
    try:
        with open(APRENDIZAJE_FILE, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[logger] Error guardando aprendizaje: {e}")

def registrar_resultado_aprendizaje(simbolo: str, pnl_usd: float,
                                     pnl_pct: float, razon_cierre: str):
    """
    Registra el resultado de una operación en el sistema de aprendizaje.
    Acumula estadísticas por activo para identificar patrones de fallo.
    """
    datos = cargar_aprendizaje()

    if simbolo not in datos:
        datos[simbolo] = {
            "total_operaciones": 0,
            "ganancias":         0,
            "perdidas":          0,
            "pnl_total":         0.0,
            "pnl_promedio":      0.0,
            "win_rate":          0.0,
            "racha_perdidas":    0,
            "max_racha_perdidas": 0,
            "ultima_operacion":  None,
            "razones_perdida":   [],
            "blacklists_total":  0,
        }

    s = datos[simbolo]
    s["total_operaciones"] += 1
    s["pnl_total"]          = round(s["pnl_total"] + pnl_usd, 2)
    s["ultima_operacion"]   = datetime.now().isoformat()

    if pnl_usd > 0:
        s["ganancias"]      += 1
        s["racha_perdidas"]  = 0
    else:
        s["perdidas"]       += 1
        s["racha_perdidas"] += 1
        s["max_racha_perdidas"] = max(s["max_racha_perdidas"], s["racha_perdidas"])
        # Guarda razón de pérdida para análisis
        if razon_cierre and len(s["razones_perdida"]) < 20:
            s["razones_perdida"].append({
                "razon":    razon_cierre[:100],
                "pnl_pct":  round(pnl_pct, 2),
                "fecha":    datetime.now().strftime("%Y-%m-%d %H:%M"),
            })

    s["win_rate"]     = round(s["ganancias"] / s["total_operaciones"] * 100, 1)
    s["pnl_promedio"] = round(s["pnl_total"] / s["total_operaciones"], 2)

    guardar_aprendizaje(datos)
    print(f"[aprendizaje] {simbolo}: win_rate={s['win_rate']}% | pnl_total=${s['pnl_total']} | ops={s['total_operaciones']}")

def registrar_blacklist_aprendizaje(simbolo: str):
    """Registra cuando un activo entra en blacklist."""
    datos = cargar_aprendizaje()
    if simbolo in datos:
        datos[simbolo]["blacklists_total"] += 1
        guardar_aprendizaje(datos)
        print(f"[aprendizaje] {simbolo}: blacklist #{datos[simbolo]['blacklists_total']}")

def obtener_activos_problematicos(win_rate_minimo: float = 40.0,
                                   operaciones_minimas: int = 3) -> list:
    """
    Retorna activos con win_rate bajo o muchas pérdidas consecutivas.
    Se usa para ajustar parámetros automáticamente.
    """
    datos = cargar_aprendizaje()
    problematicos = []

    for simbolo, stats in datos.items():
        if stats["total_operaciones"] < operaciones_minimas:
            continue
        if stats["win_rate"] < win_rate_minimo or stats["racha_perdidas"] >= 2:
            problematicos.append({
                "simbolo":         simbolo,
                "win_rate":        stats["win_rate"],
                "total_ops":       stats["total_operaciones"],
                "racha_perdidas":  stats["racha_perdidas"],
                "pnl_total":       stats["pnl_total"],
                "blacklists":      stats["blacklists_total"],
            })

    problematicos.sort(key=lambda x: x["win_rate"])
    return problematicos

def obtener_reporte_aprendizaje() -> str:
    """Genera un reporte de texto del aprendizaje acumulado."""
    datos = cargar_aprendizaje()
    if not datos:
        return "Sin datos de aprendizaje aún — se acumulan con operaciones"

    lineas = ["📚 <b>Reporte de aprendizaje:</b>\n"]
    for simbolo, s in sorted(datos.items(), key=lambda x: x[1]["win_rate"]):
        if s["total_operaciones"] == 0:
            continue
        emoji = "🟢" if s["win_rate"] >= 50 else ("🟡" if s["win_rate"] >= 35 else "🔴")
        lineas.append(
            f"{emoji} <b>{simbolo}</b>\n"
            f"   Win rate: {s['win_rate']}% | Ops: {s['total_operaciones']}\n"
            f"   P&L total: ${s['pnl_total']:+.2f} | Blacklists: {s['blacklists_total']}\n"
            f"   Racha pérdidas actual: {s['racha_perdidas']}"
        )

    problematicos = obtener_activos_problematicos()
    if problematicos:
        lineas.append(f"\n⚠️ Activos problemáticos: {', '.join([p['simbolo'] for p in problematicos])}")

    return "\n".join(lineas)

# ============================================================
# LOGS ESTÁNDAR
# ============================================================
def log_señal(simbolo: str, accion: str, precio: float, sl: float,
              tp1: float, tp2: float, confianza: float,
              fuentes: list, razon: str, horizonte: str,
              aprobada_riesgo: bool, aprobada_tendencia: bool,
              tamaño_posicion: dict = None) -> dict:

    registro = {
        "timestamp":          datetime.now().isoformat(),
        "tipo":               "SEÑAL",
        "simbolo":            simbolo,
        "accion":             accion,
        "precio":             precio,
        "stop_loss":          sl,
        "take_profit_1":      tp1,
        "take_profit_2":      tp2,
        "confianza":          confianza,
        "fuentes":            fuentes if isinstance(fuentes, str) else ",".join(fuentes),
        "razon":              razon,
        "horizonte":          horizonte,
        "aprobada_riesgo":    aprobada_riesgo,
        "aprobada_tendencia": aprobada_tendencia,
        "cantidad":           tamaño_posicion.get("cantidad", 0) if tamaño_posicion else 0,
        "valor_posicion_usd": tamaño_posicion.get("valor_posicion_usd", 0) if tamaño_posicion else 0,
        "riesgo_usd":         tamaño_posicion.get("riesgo_usd", 0) if tamaño_posicion else 0,
    }

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro) + "\n")
    except Exception as e:
        print(f"[logger] Error archivo local: {e}")

    try:
        sb = obtener_supabase()
        if sb:
            sb.table("señales_trading").insert(registro).execute()
    except Exception as e:
        print(f"[logger] Error Supabase señal: {e}")

    print(f"[logger] Señal registrada: {accion} {simbolo} @ {precio} | confianza={confianza}%")
    return registro

def log_orden(simbolo: str, accion: str, precio: float,
              cantidad: float, orden_id: str, estado: str) -> dict:

    registro = {
        "timestamp": datetime.now().isoformat(),
        "tipo":      "ORDEN",
        "simbolo":   simbolo,
        "accion":    accion,
        "precio":    precio,
        "cantidad":  cantidad,
        "orden_id":  orden_id,
        "estado":    estado,
    }

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro) + "\n")
    except:
        pass

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

    pnl_pct = round(((precio_cierre - precio_entrada) / precio_entrada) * 100, 3) if precio_entrada > 0 else 0

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

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro) + "\n")
    except:
        pass

    try:
        sb = obtener_supabase()
        if sb:
            sb.table("cierres_trading").insert(registro).execute()
    except Exception as e:
        print(f"[logger] Error Supabase cierre: {e}")

    # Registra en sistema de aprendizaje automáticamente
    registrar_resultado_aprendizaje(simbolo, pnl_usd, pnl_pct, razon_cierre)

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

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(registro) + "\n")
    except:
        pass

    print(f"[logger] Ciclo {ciclo_num}: {señales_detectadas} señales | {ordenes_ejecutadas} ordenes | {round(duracion_segundos,1)}s")
    return registro

def obtener_estadisticas_dia() -> dict:
    if not os.path.exists(LOG_FILE):
        return {
            "fecha": datetime.now().strftime("%Y-%m-%d"),
            "total_señales": 0, "total_ordenes": 0, "total_cierres": 0,
            "ganancias": 0, "perdidas": 0, "win_rate": 0,
            "pnl_total_usd": 0, "ganancia_promedio": 0, "perdida_promedio": 0,
        }

    señales = []
    ordenes = []
    cierres = []

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
        "fecha":             datetime.now().strftime("%Y-%m-%d"),
        "total_señales":     len(señales),
        "total_ordenes":     len(ordenes),
        "total_cierres":     len(cierres),
        "ganancias":         len(ganancias),
        "perdidas":          len(perdidas),
        "win_rate":          round(win_rate, 1),
        "pnl_total_usd":     round(pnl_total, 2),
        "ganancia_promedio": round(sum(ganancias)/len(ganancias), 2) if ganancias else 0,
        "perdida_promedio":  round(sum(perdidas)/len(perdidas), 2) if perdidas else 0,
    }