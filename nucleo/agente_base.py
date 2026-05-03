from abc import ABC, abstractmethod


class AgenteBase(ABC):
    def __init__(self, nombre: str):
        self.nombre = nombre

    @abstractmethod
    async def inicializar(self):
        """Prepara recursos del agente (conexiones, modelos, configuración)."""

    @abstractmethod
    async def ejecutar(self):
        """Bucle principal del agente."""

    @abstractmethod
    async def detener(self):
        """Libera recursos al apagar."""
