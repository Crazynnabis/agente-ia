import asyncio
import os
import signal
import sys
import traceback
from pathlib import Path

# Bajo pythonw.exe (Task Scheduler en background), sys.stdout es None.
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _volcar_excepcion_fatal(exc: BaseException) -> None:
    """Última red de seguridad: si todo falla, deja un .log con el traceback."""
    try:
        logs_dir = Path(__file__).parent / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        with (logs_dir / "fatal.log").open("a", encoding="utf-8") as f:
            f.write(f"\n=== {os.getpid()} cwd={os.getcwd()} ===\n")
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=f)
    except Exception:
        pass


from loguru import logger
from dotenv import load_dotenv

load_dotenv()

import uvicorn

from dashboard.servidor import crear_app
from nucleo.orquestador import Orquestador


def configurar_logger():
    logger.remove()
    if sys.stdout is not None:
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
        # bajo pythonw.exe, sys.stdout es None y el logger por defecto de
        # uvicorn falla al llamar sys.stdout.isatty(); deshabilitamos su
        # configuración de logging y dependemos de loguru.
        log_config=None,
    )
    servidor_web = uvicorn.Server(config)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(orquestador.detener()))
        except (NotImplementedError, OSError, ValueError, RuntimeError):
            # Windows / pythonw.exe sin consola: registro de señales no disponible.
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
    try:
        asyncio.run(main())
    except BaseException as _exc:
        _volcar_excepcion_fatal(_exc)
        raise
