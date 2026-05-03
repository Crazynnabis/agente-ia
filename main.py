import asyncio
import signal
import sys
sys.stdout.reconfigure(encoding="utf-8")
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

from nucleo.orquestador import Orquestador


def configurar_logger():
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
        level="INFO",
        colorize=True,
    )
    logger.add(
        "logs/agente_ia.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        encoding="utf-8",
    )


async def main():
    configurar_logger()
    logger.info("Iniciando Sistema de Agentes IA...")

    orquestador = Orquestador()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(orquestador.detener()))

    try:
        await orquestador.iniciar()
        await orquestador.ejecutar()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception(f"Error fatal en el sistema: {e}")
        sys.exit(1)
    finally:
        await orquestador.detener()
        logger.info("Sistema detenido correctamente.")


if __name__ == "__main__":
    asyncio.run(main())
