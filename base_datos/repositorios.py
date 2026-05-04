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
