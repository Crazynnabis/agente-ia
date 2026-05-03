from loguru import logger

from .cliente import get_cliente


async def guardar_inversion(datos: dict) -> None:
    try:
        cliente = await get_cliente()
        await cliente.table("Inversiones").insert(datos).execute()
    except Exception as exc:
        logger.warning(f"DB [Inversiones]: no se pudo guardar — {exc}")


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
