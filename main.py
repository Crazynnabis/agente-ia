import asyncio
import os
import signal
import sys
sys.stdout.reconfigure(encoding="utf-8")
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

import uvicorn

from dashboard.servidor import crear_app
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
    app = crear_app(orquestador)

    host = os.getenv("DASHBOARD_HOST", "127.0.0.1")
    port = int(os.getenv("DASHBOARD_PORT", "8000"))
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    servidor_web = uvicorn.Server(config)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(orquestador.detener()))
        except NotImplementedError:
            # Windows no soporta add_signal_handler para todas las señales
            pass

    try:
        await orquestador.iniciar()
        logger.info(f"Dashboard disponible en http://{host}:{port}")
        await asyncio.gather(
            orquestador.ejecutar(),
            servidor_web.serve(),
        )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception(f"Error fatal en el sistema: {e}")
        sys.exit(1)
    finally:
        servidor_web.should_exit = True
        await orquestador.detener()
        logger.info("Sistema detenido correctamente.")


if __name__ == "__main__":
    asyncio.run(main())
