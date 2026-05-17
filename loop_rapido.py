# loop_rapido.py — Ciclo de 2 minutos solo con señales urgentes
import os
import asyncio
import sys

os.environ["DOTENV_PATH"] = r'C:\Users\Oscar Hernandez\.env'
from dotenv import load_dotenv
load_dotenv(r'C:\Users\Oscar Hernandez\.env', override=True)

sys.path.insert(0, r'C:\Users\Oscar Hernandez\agente-ia')

from datetime import datetime
from agente_financiero.agente_velas import analizar_oportunidades
from agente_financiero.agente_indicadores import analizar_indicadores_completo
from agente_financiero.agente_orderflow import analizar_todos_activos
from agente_financiero.gestion_riesgo import GestorRiesgo
from agente_financiero.ejecutor_alpaca import ejecutar_orden, obtener_posiciones
from agente_financiero.alertas_telegram import alerta_señal, alerta_orden_ejecutada
from agente_financiero.logger_trading import log_señal
from agente_financiero.horario_trading import debe_operar

INTERVALO_RAPIDO = 2  # minutos
ACTIVOS          = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
gestor           = GestorRiesgo()

async def ciclo_rapido() -> dict:
    timestamp = datetime.now().strftime("%H:%M:%S")

    # Verifica horario
    horario = debe_operar()
    if not horario["operar"]:
        return {"operar": False}

    # Corre los 3 agentes mas rapidos en paralelo
    velas_res, ind_res, of_res = await asyncio.gather(
        analizar_oportunidades(),
        asyncio.to_thread(analizar_indicadores_completo),
        asyncio.to_thread(analizar_todos_activos, ACTIVOS),
    )

    señales_urgentes = []

    for ind in ind_res:
        simbolo = ind["simbolo"]

        # Señal de velas
        vela_op  = next((o for o in velas_res["oportunidades"] if simbolo in o["simbolo"]), None)
        vela_al  = next((a for a in velas_res["alertas"]       if simbolo in a["simbolo"]), None)
        señal_velas = "COMPRAR" if vela_op else ("VENDER" if vela_al else "NEUTRAL")

        # Señal de orderflow
        of = next((o for o in of_res if o.get("simbolo") == simbolo), {})
        señal_of = "COMPRAR" if "COMPRADORA" in of.get("señal","") else (
                   "VENDER"  if "VENDEDORA"  in of.get("señal","") else "NEUTRAL")

        # Señal de indicadores
        señal_ind = ind["señal"]
        confianza = ind["confianza"]

        # Solo actua si LOS 3 coinciden — maxima certeza
        if señal_velas == señal_ind == señal_of and señal_ind != "ESPERAR":
            confianza_final = min(confianza + 20, 99)

            if confianza_final >= 80:
                señales_urgentes.append({
                    "simbolo":        simbolo,
                    "señal_final":    señal_ind,
                    "precio":         ind["precio"],
                    "stop_loss":      ind["atr"]["stop_loss_largo"],
                    "take_profit_1":  ind["atr"]["take_profit_1r"],
                    "take_profit_2":  ind["atr"]["take_profit_2r"],
                    "confianza_final":confianza_final,
                    "confluencia":    "MUY_ALTA",
                    "atr_pct":        ind["atr"]["atr_pct"],
                })

    ordenes_ejecutadas = []
    for señal in señales_urgentes:
        # Verifica que no haya posicion abierta ya
        posiciones = obtener_posiciones()
        ya_abierta = any(señal["simbolo"] in p["simbolo"] for p in posiciones)
        if ya_abierta:
            continue

        # Valida riesgo
        validacion = gestor.validar_señal(señal)
        if not validacion["aprobada"]:
            continue

        t = validacion.get("tamaño", {})
        if t.get("cantidad", 0) <= 0:
            continue

        print(f"[loop_rapido] SEÑAL URGENTE: {señal['simbolo']} {señal['señal_final']} conf={señal['confianza_final']}%")

        orden = ejecutar_orden(
            simbolo=señal["simbolo"],
            accion=señal["señal_final"],
            cantidad=t["cantidad"],
            precio_entrada=señal["precio"],
            stop_loss=señal["stop_loss"],
            take_profit=señal["take_profit_1"],
            atr=señal.get("atr_pct", 0)
        )

        if "error" not in orden:
            ordenes_ejecutadas.append(orden)
            alerta_señal(
                simbolo=señal["simbolo"],
                accion=señal["señal_final"],
                precio=señal["precio"],
                sl=señal["stop_loss"],
                tp1=señal["take_profit_1"],
                confianza=señal["confianza_final"],
                razon="Ciclo rapido — 3 fuentes alineadas",
                horizonte="2min"
            )

        log_señal(
            simbolo=señal["simbolo"],
            accion=señal["señal_final"],
            precio=señal["precio"],
            sl=señal["stop_loss"],
            tp1=señal["take_profit_1"],
            tp2=señal["take_profit_2"],
            confianza=señal["confianza_final"],
            fuentes=["velas", "indicadores", "orderflow"],
            razon="Ciclo rapido urgente",
            horizonte="2min",
            aprobada_riesgo=True,
            aprobada_tendencia=True,
            tamaño_posicion=t
        )

    return {
        "timestamp":       timestamp,
        "señales_urgentes":señales_urgentes,
        "ordenes":         ordenes_ejecutadas,
    }

async def loop_rapido_principal():
    print(f"\n{'='*60}")
    print(f"LOOP RAPIDO INICIADO — Intervalo: {INTERVALO_RAPIDO} minutos")
    print(f"{'='*60}")

    ciclo = 0
    while True:
        ciclo += 1
        try:
            resultado = await ciclo_rapido()
            if resultado.get("operar") == False:
                pass
            else:
                señales = len(resultado.get("señales_urgentes", []))
                ordenes = len(resultado.get("ordenes", []))
                if señales > 0:
                    print(f"[rapido #{ciclo}] {resultado['timestamp']} — señales={señales} ordenes={ordenes}")
        except Exception as e:
            print(f"[rapido] Error ciclo #{ciclo}: {e}")

        await asyncio.sleep(INTERVALO_RAPIDO * 60)

if __name__ == "__main__":
    asyncio.run(loop_rapido_principal())