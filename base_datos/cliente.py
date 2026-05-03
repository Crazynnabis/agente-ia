import asyncio
import os

from supabase import AsyncClient, acreate_client

_cliente: AsyncClient | None = None
_lock = asyncio.Lock()


async def get_cliente() -> AsyncClient:
    global _cliente
    if _cliente is None:
        async with _lock:
            if _cliente is None:
                _cliente = await acreate_client(
                    os.environ["SUPABASE_URL"],
                    os.environ["SUPABASE_KEY"],
                )
    return _cliente
