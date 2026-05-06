from loguru import logger

from .cliente import get_cliente


async def guardar_inversion(datos: dict) -> None:
    try:
        cliente = await get_cliente()
        await cliente.table("Inversiones").insert(datos).execute()
    except Exception as exc:
        logger.warning(f"DB [Inversiones]: no se pudo guardar — {exc}")


async def obtener_analisis_previos(simbolo: str, limite: int = 5) -> list[dict]:
    try:
        cliente = await get_cliente()
        resultado = (
            await cliente.table("Inversiones")
            .select("simbolo, rendimiento_pct, volatilidad_pct, rsi, senal, analisis, created_at")
            .eq("simbolo", simbolo)
            .order("created_at", desc=True)
            .limit(limite)
            .execute()
        )
        return resultado.data or []
    except Exception as exc:
        logger.warning(f"DB [Inversiones]: no se pudo consultar historial — {exc}")
        return []


async def guardar_contenido(datos: dict) -> None:
    try:
        cliente = await get_cliente()
        await cliente.table("Contenido").insert(datos).execute()
    except Exception as exc:
        logger.warning(f"DB [Contenido]: no se pudo guardar — {exc}")


async def guardar_noticia(datos: dict) -> None:
    try:
        cliente = await get_cliente()
        await cliente.table("noticias").insert(datos).execute()
    except Exception as exc:
        logger.warning(f"DB [noticias]: no se pudo guardar — {exc}")


async def obtener_inversiones_recientes(limite: int = 10) -> list[dict]:
    try:
        cliente = await get_cliente()
        resultado = (
            await cliente.table("Inversiones")
            .select("*")
            .order("created_at", desc=True)
            .limit(limite)
            .execute()
        )
        return resultado.data or []
    except Exception as exc:
        logger.warning(f"DB [Inversiones]: no se pudieron leer recientes — {exc}")
        return []


async def obtener_contenido_reciente(limite: int = 10) -> list[dict]:
    try:
        cliente = await get_cliente()
        resultado = (
            await cliente.table("Contenido")
            .select("*")
            .order("created_at", desc=True)
            .limit(limite)
            .execute()
        )
        return resultado.data or []
    except Exception as exc:
        logger.warning(f"DB [Contenido]: no se pudieron leer recientes — {exc}")
        return []


async def obtener_noticias_recientes(limite: int = 10) -> list[dict]:
    try:
        cliente = await get_cliente()
        resultado = (
            await cliente.table("noticias")
            .select("*")
            .order("created_at", desc=True)
            .limit(limite)
            .execute()
        )
        return resultado.data or []
    except Exception as exc:
        logger.warning(f"DB [noticias]: no se pudieron leer recientes — {exc}")
        return []


async def obtener_metricas_globales() -> dict:
    cliente = await get_cliente()

    async def _contar(tabla: str) -> int:
        try:
            resultado = (
                await cliente.table(tabla)
                .select("*", count="exact", head=True)
                .execute()
            )
            return resultado.count or 0
        except Exception as exc:
            logger.warning(f"DB [{tabla}]: no se pudo contar — {exc}")
            return 0

    total_inversiones = await _contar("Inversiones")
    total_contenido = await _contar("Contenido")
    total_noticias = await _contar("noticias")

    return {
        "total_inversiones": total_inversiones,
        "total_contenido": total_contenido,
        "total_noticias": total_noticias,
        "total_general": total_inversiones + total_contenido + total_noticias,
    }
