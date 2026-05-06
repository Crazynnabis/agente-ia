from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from base_datos.repositorios import (
    obtener_contenido_reciente,
    obtener_inversiones_recientes,
    obtener_metricas_globales,
    obtener_noticias_recientes,
)
from nucleo.orquestador import Orquestador


_STATIC_DIR = Path(__file__).parent / "static"


def crear_app(orquestador: Orquestador) -> FastAPI:
    app = FastAPI(
        title="Dashboard Agentes IA",
        version="1.0.0",
        docs_url="/docs",
    )
    app.state.orquestador = orquestador

    app.mount(
        "/static",
        StaticFiles(directory=str(_STATIC_DIR)),
        name="static",
    )

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(_STATIC_DIR / "index.html")

    @app.get("/api/agentes")
    async def listar_agentes():
        return {
            "servidor_hora": datetime.now().isoformat(),
            "agentes": [a.estado_dict() for a in orquestador.agentes],
        }

    @app.get("/api/financiero/recientes")
    async def financiero_recientes(limite: int = Query(10, ge=1, le=50)):
        datos = await obtener_inversiones_recientes(limite)
        return {"total": len(datos), "items": datos}

    @app.get("/api/contenido/recientes")
    async def contenido_recientes(limite: int = Query(10, ge=1, le=50)):
        datos = await obtener_contenido_reciente(limite)
        return {"total": len(datos), "items": datos}

    @app.get("/api/turistico/recientes")
    async def turistico_recientes(limite: int = Query(10, ge=1, le=50)):
        datos = await obtener_noticias_recientes(limite)
        return {"total": len(datos), "items": datos}

    @app.get("/api/metricas")
    async def metricas():
        globales = await obtener_metricas_globales()
        agentes = orquestador.agentes
        ciclos_ok = sum(a.ciclos_completados for a in agentes)
        ciclos_err = sum(a.ciclos_con_error for a in agentes)
        total_ciclos = ciclos_ok + ciclos_err
        tasa_exito = (ciclos_ok / total_ciclos * 100) if total_ciclos else 0.0
        return {
            **globales,
            "agentes_total": len(agentes),
            "agentes_activos": sum(
                1 for a in agentes if a.estado in ("ejecutando", "esperando")
            ),
            "ciclos_completados": ciclos_ok,
            "ciclos_con_error": ciclos_err,
            "tasa_exito_pct": round(tasa_exito, 1),
        }

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "ts": datetime.now().isoformat()}

    return app
