import asyncio
from loguru import logger
from nucleo.agente_base import AgenteBase


class AgenteFinanciero(AgenteBase):
    def __init__(self):
        super().__init__("AgenteFinanciero")

    async def inicializar(self):
        logger.debug(f"{self.nombre}: cargando configuracion financiera...")

    async def ejecutar(self):
        while True:
            logger.info(f"{self.nombre}: analizando datos financieros...")
            await asyncio.sleep(30)

    async def detener(self):
        logger.debug(f"{self.nombre}: liberando recursos.")
