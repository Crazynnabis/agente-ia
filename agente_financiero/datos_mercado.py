import os
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
from loguru import logger

_CRIPTO = {"BTC", "ETH"}
_STOCKS = {"SPY", "AAPL", "NVDA", "TSLA", "MSFT"}
_BINANCE_SYMBOL = {"BTC": "BTCUSDT", "ETH": "ETHUSDT"}

_TIMEOUT = aiohttp.ClientTimeout(total=10)


async def obtener_precios_reales(simbolo: str, dias: int) -> Optional[list[float]]:
    """Devuelve precios de cierre en orden cronológico, o None si todas las fuentes fallan."""
    if simbolo in _CRIPTO:
        return await _binance_klines(simbolo, dias)
    if simbolo in _STOCKS:
        precios = await _alpaca_bars(simbolo, dias)
        if precios is None:
            precios = await _polygon_aggs(simbolo, dias)
        return precios
    return None


async def _binance_klines(simbolo: str, dias: int) -> Optional[list[float]]:
    symbol = _BINANCE_SYMBOL[simbolo]
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": "1d", "limit": dias}
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"Binance [{simbolo}]: HTTP {resp.status}")
                    return None
                data = await resp.json()
                precios = [float(k[4]) for k in data]  # índice 4 = precio de cierre
                logger.debug(f"Binance [{simbolo}]: {len(precios)} días obtenidos")
                return precios or None
        except Exception as exc:
            logger.warning(f"Binance [{simbolo}]: {exc}")
            return None


async def _alpaca_bars(simbolo: str, dias: int) -> Optional[list[float]]:
    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET", "")
    if not api_key:
        return None

    end = datetime.utcnow().date()
    # +14 para absorber fines de semana y festivos y aún obtener `dias` sesiones
    start = (datetime.utcnow() - timedelta(days=dias + 14)).date()
    url = f"https://data.alpaca.markets/v2/stocks/{simbolo}/bars"
    params = {
        "timeframe": "1Day",
        "start": str(start),
        "end": str(end),
        "limit": dias,
        "sort": "asc",
        "feed": "iex",
    }
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        try:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning(f"Alpaca [{simbolo}]: HTTP {resp.status}")
                    return None
                data = await resp.json()
                bars = data.get("bars") or []
                precios = [float(b["c"]) for b in bars]
                logger.debug(f"Alpaca [{simbolo}]: {len(precios)} días obtenidos")
                return precios or None
        except Exception as exc:
            logger.warning(f"Alpaca [{simbolo}]: {exc}")
            return None


async def _polygon_aggs(simbolo: str, dias: int) -> Optional[list[float]]:
    api_key = os.environ.get("POLYGON_API_KEY", "")
    if not api_key:
        return None

    end = datetime.utcnow().date()
    start = (datetime.utcnow() - timedelta(days=dias + 14)).date()
    url = f"https://api.polygon.io/v2/aggs/ticker/{simbolo}/range/1/day/{start}/{end}"
    params = {"apiKey": api_key, "adjusted": "true", "sort": "asc", "limit": dias}
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        try:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning(f"Polygon [{simbolo}]: HTTP {resp.status}")
                    return None
                data = await resp.json()
                results = data.get("results") or []
                precios = [float(r["c"]) for r in results]
                logger.debug(f"Polygon [{simbolo}]: {len(precios)} días obtenidos")
                return precios or None
        except Exception as exc:
            logger.warning(f"Polygon [{simbolo}]: {exc}")
            return None
