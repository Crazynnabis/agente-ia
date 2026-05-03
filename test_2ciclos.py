import asyncio
import sys
sys.stdout.reconfigure(encoding="utf-8")
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

from agente_financiero.agente import AgenteFinanciero
from agente_contenido.agente import AgenteContenido
from agente_turistico.agente import AgenteTuristico


CICLOS = 2


async def ejecutar_agente(agente, ciclos: int):
    await agente.inicializar()
    for i in range(1, ciclos + 1):
        logger.info(f"=== {agente.nombre} — ciclo {i}/{ciclos} ===")
        await agente._ciclo_analisis()
    await agente.detener()


async def main():
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )

    agentes = [AgenteFinanciero(), AgenteContenido(), AgenteTuristico()]
    logger.info(f"Iniciando {len(agentes)} agentes — {CICLOS} ciclos cada uno en paralelo")

    await asyncio.gather(*[ejecutar_agente(a, CICLOS) for a in agentes])

    logger.info("Todos los ciclos completados.")


if __name__ == "__main__":
    asyncio.run(main())
