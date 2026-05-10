# agente_financiero/digestor_tecnico.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from nucleo.cliente_ia import chat
from agente_financiero.agente_velas import analizar_oportunidades
from agente_financiero.agente_indicadores import analizar_indicadores_completo
from agente_financiero.agente_orderflow import analizar_todos_activos
from agente_financiero.agente_niveles import analizar_niveles_completo
from agente_financiero.agente_onchain import analizar_onchain_completo

ACTIVOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

async def ejecutar_ciclo_tecnico() -> dict:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[digestor_tecnico] Ciclo tecnico {timestamp}")

    print("[1/5] Analizando velas japonesas...")
    resultado_velas = await analizar_oportunidades()

    print("[2/5] Calculando indicadores avanzados...")
    resultado_indicadores = analizar_indicadores_completo()

    print("[3/5] Analizando order flow...")
    resultado_orderflow = analizar_todos_activos(ACTIVOS)

    print("[4/5] Analizando niveles clave...")
    niveles_btc = analizar_niveles_completo("BTCUSDT")
    niveles_eth = analizar_niveles_completo("ETHUSDT")

    print("[5/5] Analizando datos on-chain...")
    resultado_onchain = await analizar_onchain_completo()

    # Construye tabla de confluencia por activo
    tabla = []
    for ind in resultado_indicadores:
        simbolo = ind["simbolo"]

        # Señal de velas
        vela_oport  = next((o for o in resultado_velas["oportunidades"] if simbolo in o["simbolo"]), None)
        vela_alerta = next((a for a in resultado_velas["alertas"]       if simbolo in a["simbolo"]), None)
        señal_velas = "COMPRAR" if vela_oport else ("VENDER" if vela_alerta else "NEUTRAL")

        # Señal de orderflow
        of = next((o for o in resultado_orderflow if o.get("simbolo") == simbolo), {})
        señal_of = "COMPRAR" if "COMPRADORA" in of.get("señal","") else ("VENDER" if "VENDEDORA" in of.get("señal","") else "NEUTRAL")

        # Puntuacion total con orderflow
        señal_ind  = ind["señal"]
        confianza  = ind["confianza"]
        votos_compra = sum([
            señal_velas  == "COMPRAR",
            señal_ind    == "COMPRAR",
            señal_of     == "COMPRAR",
        ])
        votos_venta = sum([
            señal_velas  == "VENDER",
            señal_ind    == "VENDER",
            señal_of     == "VENDER",
        ])

        # Verifica contradicciones internas en indicadores
        estoc_señal = ind["estocastico"]["señal"]
        obv_señal   = ind["obv"]["tendencia"]
        wr_señal    = ind["williams_r"]["señal"]

        contradicciones_internas = sum([
            "VENTA" in estoc_señal and votos_compra >= 2,
            obv_señal == "distribucion" and votos_compra >= 2,
            "VENTA" in wr_señal and votos_compra >= 2,
        ])

        if votos_compra >= 2 and contradicciones_internas == 0:
            confluencia     = "ALTA"
            señal_final     = "COMPRAR"
            confianza_final = min(confianza + 15 + (votos_compra * 5), 99)
        elif votos_compra >= 2 and contradicciones_internas == 1:
            confluencia     = "MEDIA"
            señal_final     = "COMPRAR"
            confianza_final = min(confianza, 70)
        elif votos_venta >= 2:
            confluencia     = "ALTA"
            señal_final     = "VENDER"
            confianza_final = min(confianza + 15 + (votos_venta * 5), 99)
        else:
            confluencia     = "BAJA"
            señal_final     = "ESPERAR"
            confianza_final = max(confianza - 20, 10)

        tabla.append({
            "simbolo":         simbolo,
            "precio":          ind["precio"],
            "señal_final":     señal_final,
            "confluencia":     confluencia,
            "confianza_final": confianza_final,
            "votos_compra":    votos_compra,
            "votos_venta":     votos_venta,
            "señal_velas":     señal_velas,
            "señal_ind":       señal_ind,
            "señal_of":        señal_of,
            "orderflow":       of.get("señal", "N/A"),
            "of_ratio":        of.get("ratio_compra_venta", "N/A"),
            "of_delta":        of.get("delta_pct", "N/A"),
            "stop_loss":       ind["atr"]["stop_loss_largo"],
            "take_profit_1":   ind["atr"]["take_profit_1r"],
            "take_profit_2":   ind["atr"]["take_profit_2r"],
            "atr_pct":         ind["atr"]["atr_pct"],
            "macd_cruce":      ind["macd"].get("cruce"),
            "macd_div":        ind["macd"].get("divergencia"),
            "estocastico":     ind["estocastico"]["señal"],
            "vwap":            ind["vwap"]["posicion"],
            "obv":             ind["obv"]["tendencia"],
            "williams":        ind["williams_r"]["señal"],
        })

    señales_fuertes = [t for t in tabla if t["confluencia"] == "ALTA" and t["confianza_final"] >= 65]

    # Contexto on-chain para decision
    onchain_resumen = f"""
Dominancia BTC: {resultado_onchain['flujo'].get('dominancia_btc','N/A')}%
Fee BTC: {resultado_onchain['btc'].get('fee_rapido','N/A')} sat/vB
Señales: {', '.join(resultado_onchain['señales'].get('señales',['N/A']))}
"""

    # Niveles clave
    niveles_resumen = f"""
BTC contexto: {niveles_btc['zonas_diario'].get('contexto','N/A')} | dist_resistencia={niveles_btc['zonas_diario'].get('dist_resistencia_pct','N/A')}%
ETH contexto: {niveles_eth['zonas_diario'].get('contexto','N/A')} | dist_soporte={niveles_eth['zonas_diario'].get('dist_soporte_pct','N/A')}%
"""

    # Resumen completo para IA
    resumen_tabla = "\n".join([
        f"{t['simbolo']}: {t['señal_final']} | confianza={t['confianza_final']}% | "
        f"votos_compra={t['votos_compra']} votos_venta={t['votos_venta']} | "
        f"precio={t['precio']} | SL={t['stop_loss']} | TP1={t['take_profit_1']} | TP2={t['take_profit_2']} | "
        f"velas={t['señal_velas']} ind={t['señal_ind']} of={t['señal_of']} | "
        f"MACD={t['macd_cruce']} div={t['macd_div']} | "
        f"Estoc={t['estocastico']} VWAP={t['vwap']} OBV={t['obv']} WR={t['williams']}"
        for t in tabla
    ])

    print("[digestor_tecnico] Generando decisiones ejecutables con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"TABLA DE CONFLUENCIA:\n{resumen_tabla}\n\nCONTEXTO ON-CHAIN:\n{onchain_resumen}\n\nNIVELES CLAVE:\n{niveles_resumen}"}],
        system="""Eres el digestor tecnico de un sistema de trading automatico profesional.
Recibes datos de 5 fuentes: velas japonesas, indicadores tecnicos, order flow, niveles institucionales y datos on-chain.
Entrega SOLO decisiones ejecutables con confluencia ALTA y confianza mayor a 65%.

Formato exacto para cada decision:
DECISION_N:
- ACCION: COMPRAR o VENDER
- SIMBOLO: nombre exacto
- PRECIO_ENTRADA: numero
- STOP_LOSS: numero (usa ATR dinamico)
- TAKE_PROFIT_1: numero (relacion riesgo/beneficio minimo 1:2)
- TAKE_PROFIT_2: numero (relacion riesgo/beneficio minimo 1:3)
- CONFIANZA: porcentaje
- FUENTES_CONFIRMACION: lista de fuentes que confirman la señal
- RAZON: una sola oracion clara
- HORIZONTE: 5min o 15min o 1hora

Si no hay señales con alta confluencia responde exactamente: SIN_SEÑALES_FUERTES
Responde en español sin texto adicional.""",
        max_tokens=800
    )

    return {
        "timestamp":       timestamp,
        "tabla":           tabla,
        "señales_fuertes": señales_fuertes,
        "onchain":         resultado_onchain["señales"],
        "decisiones":      respuesta["texto"],
        "modelo":          respuesta["modelo"],
    }