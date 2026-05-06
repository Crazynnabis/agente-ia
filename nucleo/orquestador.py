import asyncio
from loguru import logger

from agente_financiero.agente import AgenteFinanciero
from agente_contenido.agente import AgenteContenido
from agente_turistico.agente import AgenteTuristico


class Orquestador:
    def __init__(self):
        self.agentes = [
            AgenteFinanciero(),
            AgenteContenido(),
            AgenteTuristico(),
        ]
        self._tareas: list[asyncio.Task] = []
        self._activo = False

    async def iniciar(self):
        logger.info(f"Inicializando {len(self.agentes)} agentes...")
        for agente in self.agentes:
            await agente.inicializar()
            agente.estado = "inicializado"
            logger.info(f"  [OK] {agente.nombre} listo")

    async def ejecutar(self):
        self._activo = True
        logger.info("Todos los agentes en ejecucion. Presiona Ctrl+C para detener.")
        self._tareas = [
            asyncio.create_task(agente.ejecutar(), name=agente.nombre)
            for agente in self.agentes
        ]
        await asyncio.gather(*self._tareas, return_exceptions=True)

    async def detener(self):
        if not self._activo:
            return
        self._activo = False
        logger.info("Deteniendo agentes...")
        for tarea in self._tareas:
            tarea.cancel()
        await asyncio.gather(*self._tareas, return_exceptions=True)
        for agente in self.agentes:
            await agente.detener()
            agente.estado = "detenido"
