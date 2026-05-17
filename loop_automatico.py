# loop_automatico.py
import os
import sys

# Carga credenciales ANTES de cualquier otro import
os.environ["DOTENV_PATH"] = r'C:\Users\Oscar Hernandez\.env'
from dotenv import load_dotenv
load_dotenv(r'C:\Users\Oscar Hernandez\.env', override=True)

sys.path.insert(0, r'C:\Users\Oscar Hernandez\agente-ia')

import asyncio
from datetime import datetime
from agente_financiero.digestor_maestro import ejecutar_ciclo_maestro
from agente_financiero.alertas_telegram import enviar_mensaje, alerta_resumen_dia
from agente_financiero.logger_trading import obtener_estadisticas_dia

INTERVALO_MINUTOS = 15
MAX_CICLOS        = 0

async def loop_principal():
    ciclo = 0
    print(f"\n{'='*60}")
    print(f"LOOP AUTOMATICO INICIADO")
    print(f"Intervalo: {INTERVALO_MINUTOS} minutos")
    print(f"{'='*60}")

    enviado = enviar_mensaje(
        f"🤖 <b>Sistema de Trading IA iniciado</b>\n"
        f"Intervalo: {INTERVALO_MINUTOS} minutos\n"
        f"Hora: {datetime.now().strftime('%H:%M:%S')}"
    )
    print(f"[loop] Telegram: {'OK' if enviado else 'ERROR'}")

    while True:
        ciclo += 1
        print(f"\n{'='*60}")
        print(f"CICLO #{ciclo} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}")

        try:
            resultado = await ejecutar_ciclo_maestro()

            if not resultado.get("operar", True):
                print(f"[loop] Fuera de horario — {resultado.get('razon','')}")
                await asyncio.sleep(INTERVALO_MINUTOS * 60)
                continue

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

        print(f"\n[loop] Esperando {INTERVALO_MINUTOS} minutos...")
        await asyncio.sleep(INTERVALO_MINUTOS * 60)

if __name__ == "__main__":
    asyncio.run(loop_principal())