import asyncio
from loguru import logger
from nucleo.agente_base import AgenteBase


class AgenteTuristico(AgenteBase):
    def __init__(self):
        super().__init__("AgenteTuristico")

    async def inicializar(self):
        logger.debug(f"{self.nombre}: cargando datos turisticos...")

    async def ejecutar(self):
        while True:
            logger.info(f"{self.nombre}: generando recomendaciones turisticas...")
            await asyncio.sleep(60)

    async def detener(self):
        logger.debug(f"{self.nombre}: liberando recursos.")
