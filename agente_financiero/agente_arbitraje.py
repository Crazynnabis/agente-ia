# agente_financiero/agente_arbitraje.py
import numpy as np
import pandas as pd
from datetime import datetime
from agente_financiero.cache_mercado import obtener_velas

# Pares con alta correlacion historica
PARES_ARBITRAJE = [
    ("BTCUSDT", "ETHUSDT"),
    ("ETHUSDT", "SOLUSDT"),
    ("BTCUSDT", "BNBUSDT"),
]

def obtener_spread_historico(simbolo_a: str, simbolo_b: str, ventana: int = 100) -> dict:
    try:
        df_a = obtener_velas(simbolo_a, "1h", ventana)
        df_b = obtener_velas(simbolo_b, "1h", ventana)

        if df_a.empty or df_b.empty:
            return {"error": "Sin datos"}

        closes_a = df_a["close"].values
        closes_b = df_b["close"].values

        min_len  = min(len(closes_a), len(closes_b))
        closes_a = closes_a[-min_len:]
        closes_b = closes_b[-min_len:]

        # Ratio entre los dos activos
        ratio       = closes_a / closes_b
        ratio_media = np.mean(ratio)
        ratio_std   = np.std(ratio)
        ratio_actual = float(ratio[-1])

        # Z-Score del ratio
        zscore = (ratio_actual - ratio_media) / ratio_std if ratio_std > 0 else 0

        # Correlacion historica
        ret_a = np.diff(closes_a) / closes_a[:-1]
        ret_b = np.diff(closes_b) / closes_b[:-1]
        correlacion = float(np.corrcoef(ret_a, ret_b)[0, 1])

        # Señal de arbitraje
        señal       = "ESPERAR"
        accion_a    = "ESPERAR"
        accion_b    = "ESPERAR"
        fuerza      = "baja"
        razon       = ""

        if zscore > 2.0:
            # Ratio muy alto — A sobrevaluado vs B
            señal    = "ARBITRAJE_RATIO_ALTO"
            accion_a = "VENDER"
            accion_b = "COMPRAR"
            fuerza   = "muy_alta"
            razon    = f"Ratio {round(ratio_actual,4)} es {round(zscore,2)} desv sobre media — {simbolo_a} sobrevaluado vs {simbolo_b}"
        elif zscore > 1.5:
            señal    = "SESGO_RATIO_ALTO"
            accion_a = "VENDER"
            accion_b = "COMPRAR"
            fuerza   = "alta"
            razon    = f"Ratio {round(ratio_actual,4)} elevado ({round(zscore,2)} desv) — posible reversion"
        elif zscore < -2.0:
            # Ratio muy bajo — A subvaluado vs B
            señal    = "ARBITRAJE_RATIO_BAJO"
            accion_a = "COMPRAR"
            accion_b = "VENDER"
            fuerza   = "muy_alta"
            razon    = f"Ratio {round(ratio_actual,4)} es {round(abs(zscore),2)} desv bajo media — {simbolo_a} subvaluado vs {simbolo_b}"
        elif zscore < -1.5:
            señal    = "SESGO_RATIO_BAJO"
            accion_a = "COMPRAR"
            accion_b = "VENDER"
            fuerza   = "alta"
            razon    = f"Ratio {round(ratio_actual,4)} bajo ({round(abs(zscore),2)} desv) — posible reversion"

        # Solo opera si correlacion es alta
        if abs(correlacion) < 0.7:
            señal    = "CORRELACION_BAJA"
            accion_a = "ESPERAR"
            accion_b = "ESPERAR"
            fuerza   = "ninguna"
            razon    = f"Correlacion {round(correlacion,3)} insuficiente para arbitraje"

        precio_a = float(closes_a[-1])
        precio_b = float(closes_b[-1])

        # TP y SL basados en reversion al promedio
        distancia_reversion = abs(ratio_actual - ratio_media) * precio_b
        sl_a  = precio_a * 1.02 if accion_a == "VENDER" else precio_a * 0.98
        tp1_a = precio_a * 0.99 if accion_a == "VENDER" else precio_a * 1.01

        return {
            "par":          f"{simbolo_a}/{simbolo_b}",
            "simbolo_a":    simbolo_a,
            "simbolo_b":    simbolo_b,
            "precio_a":     round(precio_a, 4),
            "precio_b":     round(precio_b, 4),
            "ratio_actual": round(ratio_actual, 6),
            "ratio_media":  round(float(ratio_media), 6),
            "ratio_std":    round(float(ratio_std), 6),
            "zscore":       round(zscore, 3),
            "correlacion":  round(correlacion, 3),
            "señal":        señal,
            "accion_a":     accion_a,
            "accion_b":     accion_b,
            "fuerza":       fuerza,
            "razon":        razon,
            "sl_a":         round(sl_a, 4),
            "tp1_a":        round(tp1_a, 4),
            "timestamp":    datetime.now().strftime("%H:%M:%S"),
        }
    except Exception as e:
        return {"error": str(e)}

def ejecutar_arbitraje() -> list:
    resultados = []
    for sim_a, sim_b in PARES_ARBITRAJE:
        print(f"[agente_arbitraje] Analizando {sim_a}/{sim_b}...")
        r = obtener_spread_historico(sim_a, sim_b)
        if "error" not in r:
            resultados.append(r)
    return resultados

def obtener_reporte_arbitraje() -> str:
    resultados = ejecutar_arbitraje()
    lineas = []
    for r in resultados:
        if r.get("fuerza") in ["alta", "muy_alta"]:
            lineas.append(
                f"{r['par']}: {r['señal']} | Z={r['zscore']} | "
                f"corr={r['correlacion']} | {r['accion_a']} {r['simbolo_a']} / "
                f"{r['accion_b']} {r['simbolo_b']}"
            )
    return "\n".join(lineas) if lineas else "Sin oportunidades de arbitraje"