from abc import ABC, abstractmethod
from datetime import datetime


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class AgenteBase(ABC):
    def __init__(self, nombre: str):
        self.nombre = nombre
        self.estado: str = "creado"
        self.ciclos_completados: int = 0
        self.ciclos_con_error: int = 0
        self.ultimo_ciclo_inicio: datetime | None = None
        self.ultimo_ciclo_fin: datetime | None = None
        self.ultima_tarea: str | None = None
        self.ultimo_error: str | None = None

    @abstractmethod
    async def inicializar(self):
        """Prepara recursos del agente (conexiones, modelos, configuración)."""

    @abstractmethod
    async def ejecutar(self):
        """Bucle principal del agente."""

    @abstractmethod
    async def detener(self):
        """Libera recursos al apagar."""

    def _marcar_inicio(self, tarea: str) -> None:
        self.ultima_tarea = tarea
        self.ultimo_ciclo_inicio = datetime.now()
        self.estado = "ejecutando"

    def _marcar_fin_ok(self) -> None:
        self.ultimo_ciclo_fin = datetime.now()
        self.ciclos_completados += 1
        self.ultimo_error = None
        self.estado = "esperando"

    def _marcar_error(self, exc: BaseException) -> None:
        self.ultimo_ciclo_fin = datetime.now()
        self.ciclos_con_error += 1
        self.ultimo_error = f"{type(exc).__name__}: {exc}"
        self.estado = "error"

    def estado_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "estado": self.estado,
            "ciclos_completados": self.ciclos_completados,
            "ciclos_con_error": self.ciclos_con_error,
            "ultimo_ciclo_inicio": _iso(self.ultimo_ciclo_inicio),
            "ultimo_ciclo_fin": _iso(self.ultimo_ciclo_fin),
            "ultima_tarea": self.ultima_tarea,
            "ultimo_error": self.ultimo_error,
        }
