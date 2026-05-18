# loop_automatico.py — Loop dual integrado 2min + 15min
import os
import sys
import asyncio

os.environ["DOTENV_PATH"] = r'C:\Users\Oscar Hernandez\.env'
from dotenv import load_dotenv
load_dotenv(r'C:\Users\Oscar Hernandez\.env', override=True)

sys.path.insert(0, r'C:\Users\Oscar Hernandez\agente-ia')

from datetime import datetime
from supabase import create_client
from agente_financiero.digestor_maestro import ejecutar_ciclo_maestro
from agente_financiero.alertas_telegram import enviar_mensaje, alerta_resumen_dia, alerta_señal
from agente_financiero.logger_trading import obtener_estadisticas_dia, log_señal
from agente_financiero.horario_trading import debe_operar
from agente_financiero.agente_velas import analizar_oportunidades
from agente_financiero.agente_indicadores import analizar_indicadores_completo
from agente_financiero.agente_orderflow import analizar_todos_activos
from agente_financiero.gestion_riesgo import GestorRiesgo
from agente_financiero.ejecutor_alpaca import ejecutar_orden, obtener_posiciones

INTERVALO_MINUTOS = 15
MAX_CICLOS        = 0
ACTIVOS_RAPIDO    = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
gestor_rapido     = GestorRiesgo()

async def ciclo_rapido_integrado():
    try:
        if not debe_operar()["operar"]:
            return

        velas_res, ind_res, of_res = await asyncio.gather(
            analizar_oportunidades(),
            asyncio.to_thread(analizar_indicadores_completo),
            asyncio.to_thread(analizar_todos_activos, ACTIVOS_RAPIDO),
        )

        for ind in ind_res:
            simbolo   = ind["simbolo"]
            señal_ind = ind["señal"]
            confianza = ind["confianza"]

            vela_op    = next((o for o in velas_res["oportunidades"] if simbolo in o["simbolo"]), None)
            of         = next((o for o in of_res if o.get("simbolo") == simbolo), {})
            señal_of   = "COMPRAR" if "COMPRADORA" in of.get("señal","") else (
                         "VENDER"  if "VENDEDORA"  in of.get("señal","") else "NEUTRAL")
            señal_velas = "COMPRAR" if vela_op else "NEUTRAL"

            if señal_velas == señal_ind == señal_of and señal_ind != "ESPERAR" and confianza >= 80:
                posiciones = obtener_posiciones()
                ya_abierta = any(simbolo in p["simbolo"] for p in posiciones)
                if ya_abierta:
                    continue

                señal_data = {
                    "simbolo":        simbolo,
                    "señal_final":    señal_ind,
                    "precio":         ind["precio"],
                    "stop_loss":      ind["atr"]["stop_loss_largo"],
                    "take_profit_1":  ind["atr"]["take_profit_1r"],
                    "take_profit_2":  ind["atr"]["take_profit_2r"],
                    "confianza_final":min(confianza + 20, 99),
                }
                validacion = gestor_rapido.validar_señal(señal_data)
                if not validacion["aprobada"]:
                    continue

                t = validacion.get("tamaño", {})
                if t.get("cantidad", 0) <= 0:
                    continue

                print(f"[rapido] SEÑAL URGENTE: {simbolo} {señal_ind} conf={min(confianza+20,99)}%")
                orden = ejecutar_orden(
                    simbolo=simbolo,
                    accion=señal_ind,
                    cantidad=t["cantidad"],
                    precio_entrada=ind["precio"],
                    stop_loss=ind["atr"]["stop_loss_largo"],
                    take_profit=ind["atr"]["take_profit_1r"],
                    atr=ind.get("atr_pct", 0)
                )
                if "error" not in orden:
                    alerta_señal(
                        simbolo=simbolo,
                        accion=señal_ind,
                        precio=ind["precio"],
                        sl=ind["atr"]["stop_loss_largo"],
                        tp1=ind["atr"]["take_profit_1r"],
                        confianza=min(confianza+20, 99),
                        razon="Ciclo rapido — 3 fuentes alineadas",
                        horizonte="2min"
                    )
    except Exception as e:
        print(f"[rapido] Error: {e}")

async def loop_principal():
    ciclo = 0
    print(f"\n{'='*60}")
    print(f"LOOP AUTOMATICO DUAL INICIADO")
    print(f"Ciclo lento: {INTERVALO_MINUTOS} minutos | Ciclo rapido: 2 minutos")
    print(f"{'='*60}")

    enviado = enviar_mensaje(
        f"🤖 <b>Sistema de Trading IA iniciado</b>\n"
        f"Ciclo lento: {INTERVALO_MINUTOS}min | Ciclo rapido: 2min\n"
        f"Hora: {datetime.now().strftime('%H:%M:%S')}"
    )
    print(f"[loop] Telegram: {'OK' if enviado else 'ERROR'}")

    while True:
        ciclo += 1
        print(f"\n{'='*60}")
        print(f"CICLO LENTO #{ciclo} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        try:
            resultado = await ejecutar_ciclo_maestro()

            if not resultado.get("operar", True):
                print(f"[loop] Fuera de horario — {resultado.get('razon','')}")
            else:
                señales  = len(resultado.get("señales_aprobadas", []))
                ordenes  = len(resultado.get("ordenes_ejecutadas", []))
                duracion = resultado.get("duracion_segundos", 0)
                print(f"\n[loop] Ciclo #{ciclo}: señales={señales} ordenes={ordenes} duracion={duracion}s")

                if ordenes > 0:
                    for orden in resultado.get("ordenes_ejecutadas", []):
                        if "error" not in orden:
                            enviar_mensaje(
                                f"✅ Orden ejecutada ciclo #{ciclo}\n"
                                f"Simbolo: {orden.get('simbolo')}\n"
                                f"Accion: {orden.get('accion')}\n"
                                f"Precio: {orden.get('precio')}"
                            )

                if ciclo % 4 == 0:
                    stats = obtener_estadisticas_dia()
                    alerta_resumen_dia(stats)

            if MAX_CICLOS > 0 and ciclo >= MAX_CICLOS:
                break

        except KeyboardInterrupt:
            print("\n[loop] Detenido por usuario")
            enviar_mensaje("⛔ Sistema de Trading IA detenido")
            break
        except Exception as e:
            print(f"[loop] Error ciclo #{ciclo}: {e}")
            enviar_mensaje(f"⚠️ Error ciclo #{ciclo}: {str(e)[:100]}")

        # Ping a Supabase cada 5 dias
        if ciclo % 480 == 0:
            try:
                sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
                sb.table("señales_trading").select("id").limit(1).execute()
                print("[loop] Ping Supabase OK")
            except Exception as e:
                print(f"[loop] Ping Supabase error: {e}")

        # Ciclos rapidos cada 2 minutos mientras espera el ciclo completo
        print(f"\n[loop] Iniciando {INTERVALO_MINUTOS // 2} ciclos rapidos de 2 minutos...")
        for i in range(INTERVALO_MINUTOS // 2):
            await asyncio.sleep(2 * 60)
            print(f"[rapido] Ciclo rapido {i+1}/{INTERVALO_MINUTOS // 2} — {datetime.now().strftime('%H:%M:%S')}")
            await ciclo_rapido_integrado()

if __name__ == "__main__":
    asyncio.run(loop_principal())