# agente_financiero/digestor_tecnico.py
import ollama
from datetime import datetime
from agente_financiero.agente_velas import analizar_oportunidades
from agente_financiero.agente_indicadores import analizar_indicadores_completo

def ejecutar_ciclo_tecnico() -> dict:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[digestor_tecnico] Ciclo tecnico {timestamp}")

    print("[1/2] Analizando velas japonesas...")
    resultado_velas = analizar_oportunidades()

    print("[2/2] Calculando indicadores avanzados...")
    resultado_indicadores = analizar_indicadores_completo()

    # Construye tabla de confluencia
    tabla = []
    for ind in resultado_indicadores:
        simbolo = ind["simbolo"]

        # Busca señal de velas para este simbolo
        vela_oport = next(
            (o for o in resultado_velas["oportunidades"] if simbolo in o["simbolo"]),
            None
        )
        vela_alerta = next(
            (a for a in resultado_velas["alertas"] if simbolo in a["simbolo"]),
            None
        )

        señal_velas = "COMPRAR" if vela_oport else ("VENDER" if vela_alerta else "NEUTRAL")
        señal_ind   = ind["señal"]
        confianza   = ind["confianza"]

        # Confluencia: ambos coinciden = alta certeza
        if señal_velas == señal_ind:
            confluencia = "ALTA"
            confianza_final = min(confianza + 15, 99)
        elif señal_velas == "NEUTRAL" or señal_ind == "ESPERAR":
            confluencia = "MEDIA"
            confianza_final = confianza
        else:
            confluencia = "BAJA_CONTRADICCION"
            confianza_final = max(confianza - 20, 10)

        tabla.append({
            "simbolo":         simbolo,
            "precio":          ind["precio"],
            "señal_velas":     señal_velas,
            "señal_ind":       señal_ind,
            "confluencia":     confluencia,
            "confianza_final": confianza_final,
            "stop_loss":       ind["atr"]["stop_loss_largo"],
            "take_profit":     ind["atr"]["take_profit_1r"],
            "take_profit_2":   ind["atr"]["take_profit_2r"],
            "atr_pct":         ind["atr"]["atr_pct"],
            "macd_cruce":      ind["macd"].get("cruce"),
            "macd_div":        ind["macd"].get("divergencia"),
            "estocastico":     ind["estocastico"]["señal"],
            "vwap":            ind["vwap"]["posicion"],
            "obv":             ind["obv"]["tendencia"],
            "williams":        ind["williams_r"]["señal"],
        })

    # Filtra solo señales de alta confluencia
    señales_fuertes = [t for t in tabla if t["confluencia"] == "ALTA" and t["confianza_final"] >= 65]
    contradicciones = [t for t in tabla if t["confluencia"] == "BAJA_CONTRADICCION"]

    # Resumen para Ollama
    resumen = "\n".join([
        f"{t['simbolo']}: {t['señal_ind']} | confluencia={t['confluencia']} | "
        f"confianza={t['confianza_final']}% | precio={t['precio']} | "
        f"SL={t['stop_loss']} | TP1={t['take_profit']} | TP2={t['take_profit_2']} | "
        f"MACD_cruce={t['macd_cruce']} | MACD_div={t['macd_div']} | "
        f"Estoc={t['estocastico']} | VWAP={t['vwap']} | OBV={t['obv']} | WR={t['williams']}"
        for t in tabla
    ])

    print("[digestor_tecnico] Generando decision ejecutable...")
    respuesta = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "system",
                "content": """Eres el digestor tecnico de un sistema de trading automatico.
Recibes datos de velas japonesas e indicadores avanzados ya calculados.
Tu unica funcion es entregar decisiones ejecutables en este formato exacto:

DECISION_1:
- ACCION: COMPRAR o VENDER o ESPERAR
- SIMBOLO: nombre
- PRECIO_ENTRADA: numero
- STOP_LOSS: numero
- TAKE_PROFIT_1: numero
- TAKE_PROFIT_2: numero
- CONFIANZA: porcentaje
- RAZON: una sola oracion
- HORIZONTE: 5min o 15min o 1hora

Solo incluye decisiones con confluencia ALTA y confianza mayor a 65%.
Si no hay señales fuertes, responde: SIN_SEÑALES_FUERTES
Responde en español, sin texto adicional."""
            },
            {
                "role": "user",
                "content": f"ANALISIS TECNICO COMPLETO:\n{resumen}"
            }
        ]
    )

    decisiones_texto = respuesta["message"]["content"]

    return {
        "timestamp":       timestamp,
        "tabla":           tabla,
        "señales_fuertes": señales_fuertes,
        "contradicciones": contradicciones,
        "decisiones":      decisiones_texto,
    }