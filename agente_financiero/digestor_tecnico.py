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

    # Inicializa siempre — evita NameError si cualquier agente falla
    tabla           = []
    señales_fuertes = []

    try:
        print("[1/5] Analizando velas japonesas...")
        resultado_velas = await analizar_oportunidades()

        print("[2/5] Calculando indicadores avanzados...")
        resultado_indicadores = analizar_indicadores_completo()

        print("[3/5] Analizando order flow...")
        resultado_orderflow = analizar_todos_activos(ACTIVOS)

        print("[4/5] Analizando niveles clave y on-chain en paralelo...")
        niveles_btc, niveles_eth, resultado_onchain = await asyncio.gather(
            asyncio.to_thread(analizar_niveles_completo, "BTCUSDT"),
            asyncio.to_thread(analizar_niveles_completo, "ETHUSDT"),
            analizar_onchain_completo(),
        )

        for ind in resultado_indicadores:
            simbolo = ind["simbolo"]

            vela_oport  = next((o for o in resultado_velas["oportunidades"] if simbolo in o["simbolo"]), None)
            vela_alerta = next((a for a in resultado_velas["alertas"]       if simbolo in a["simbolo"]), None)
            señal_velas = "COMPRAR" if vela_oport else ("VENDER" if vela_alerta else "NEUTRAL")

            of       = next((o for o in resultado_orderflow if o.get("simbolo") == simbolo), {})
            señal_of = "COMPRAR" if "COMPRADORA" in of.get("señal","") else (
                       "VENDER"  if "VENDEDORA"  in of.get("señal","") else "NEUTRAL")

            señal_ind = ind["señal"]
            confianza = ind["confianza"]

            votos_compra = sum([
                señal_velas == "COMPRAR",
                señal_ind   == "COMPRAR",
                señal_of    == "COMPRAR",
            ])
            votos_venta = sum([
                señal_velas == "VENDER",
                señal_ind   == "VENDER",
                señal_of    == "VENDER",
            ])

            estoc_señal = ind["estocastico"]["señal"]
            obv_señal   = ind["obv"]["tendencia"]
            wr_señal    = ind["williams_r"]["señal"]

            contradicciones = sum([
                "VENTA" in estoc_señal and votos_compra >= 2,
                obv_señal == "distribucion" and votos_compra >= 2,
                "VENTA" in wr_señal and votos_compra >= 2,
            ])

            if votos_compra >= 2 and contradicciones == 0:
                confluencia     = "ALTA"
                señal_final     = "COMPRAR"
                confianza_final = min(confianza + 15 + (votos_compra * 5), 99)
            elif votos_venta >= 2 and contradicciones == 0:
                confluencia     = "ALTA"
                señal_final     = "VENDER"
                confianza_final = min(confianza + 15 + (votos_venta * 5), 99)
            elif votos_compra >= 2 and contradicciones == 1:
                confluencia     = "MEDIA"
                señal_final     = "COMPRAR"
                confianza_final = min(confianza, 75)
            elif votos_venta >= 2 and contradicciones == 1:
                confluencia     = "MEDIA"
                señal_final     = "VENDER"
                confianza_final = min(confianza, 75)
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

        señales_fuertes = [
            t for t in tabla
            if t["confluencia"] == "ALTA" and t["confianza_final"] >= 80
        ]

        onchain_resumen = f"""
Dominancia BTC: {resultado_onchain['flujo'].get('dominancia_btc','N/A')}%
Fee BTC: {resultado_onchain['btc'].get('fee_rapido','N/A')} sat/vB
Señales: {', '.join(resultado_onchain['señales'].get('señales',['N/A']))}
"""
        niveles_resumen = f"""
BTC: {niveles_btc['zonas_diario'].get('contexto','N/A')} | dist_resistencia={niveles_btc['zonas_diario'].get('dist_resistencia_pct','N/A')}%
ETH: {niveles_eth['zonas_diario'].get('contexto','N/A')} | dist_soporte={niveles_eth['zonas_diario'].get('dist_soporte_pct','N/A')}%
"""

    except Exception as e:
        print(f"[digestor_tecnico] Error en agentes: {e}")
        onchain_resumen = "Sin datos onchain"
        niveles_resumen = "Sin datos niveles"

    resumen_tabla = "\n".join([
        f"{t['simbolo']}: {t['señal_final']} | conf={t['confianza_final']}% | "
        f"C={t['votos_compra']} V={t['votos_venta']} | precio={t['precio']} | "
        f"SL={t['stop_loss']} TP1={t['take_profit_1']} TP2={t['take_profit_2']} | "
        f"velas={t['señal_velas']} ind={t['señal_ind']} of={t['señal_of']} | "
        f"MACD={t['macd_cruce']} Estoc={t['estocastico']} VWAP={t['vwap']} OBV={t['obv']}"
        for t in tabla
    ]) if tabla else "Sin datos disponibles"

    print("[digestor_tecnico] Generando decisiones ejecutables con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"TABLA:\n{resumen_tabla}\n\nON-CHAIN:\n{onchain_resumen}\n\nNIVELES:\n{niveles_resumen}"}],
        system="""Eres el digestor tecnico de un sistema de trading automatico profesional.
Recibes datos de 5 fuentes: velas japonesas, indicadores tecnicos, order flow, niveles institucionales y datos on-chain de BTC ETH SOL BNB.
Entrega SOLO decisiones con confluencia ALTA y confianza MAYOR A 80%.
Formato:
DECISION_N:
- ACCION: COMPRAR o VENDER
- SIMBOLO: nombre exacto
- PRECIO_ENTRADA: numero
- STOP_LOSS: numero
- TAKE_PROFIT_1: numero (ratio minimo 2:1)
- TAKE_PROFIT_2: numero (ratio minimo 3:1)
- CONFIANZA: porcentaje
- FUENTES: velas/indicadores/orderflow que confirman
- RAZON: una oracion con niveles especificos de soporte y resistencia
- HORIZONTE: 5min o 15min o 1hora
Si no hay señales: SIN_SEÑALES_FUERTES
Responde en español sin texto adicional.""",
        max_tokens=600
    )

    return {
        "timestamp":       timestamp,
        "tabla":           tabla,
        "señales_fuertes": señales_fuertes,
        "onchain":         resultado_onchain["señales"] if tabla else {},
        "decisiones":      respuesta["texto"],
        "modelo":          respuesta["modelo"],
    }