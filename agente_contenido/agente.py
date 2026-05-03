import asyncio
from loguru import logger
from nucleo.agente_base import AgenteBase


class AgenteContenido(AgenteBase):
    def __init__(self):
        super().__init__("AgenteContenido")

    async def inicializar(self):
        logger.debug(f"{self.nombre}: cargando modelos de contenido...")

    async def ejecutar(self):
        while True:
            logger.info(f"{self.nombre}: procesando contenido...")
            await asyncio.sleep(45)

    async def detener(self):
        logger.debug(f"{self.nombre}: liberando recursos.")
