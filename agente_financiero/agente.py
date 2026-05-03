import asyncio
import json
import random
from datetime import datetime
from typing import Any

import anthropic
from loguru import logger

from base_datos.repositorios import guardar_inversion
from nucleo.agente_base import AgenteBase


SISTEMA = """Eres un agente financiero experto. Tu función es analizar activos financieros,
calcular métricas de riesgo y rendimiento, e identificar señales de mercado relevantes.

Proceso de análisis:
1. Obtén los datos históricos del activo con `obtener_datos_mercado`.
2. Calcula las métricas financieras con `calcular_metricas`.
3. Redacta un análisis conciso (máximo 4 oraciones) con: rendimiento, nivel de riesgo,
   señal RSI y recomendación clara (comprar / mantener / vender)."""

PORTAFOLIO = ["BTC", "ETH", "SPY", "AAPL", "NVDA", "TSLA", "MSFT"]

HERRAMIENTAS = [
    {
        "name": "obtener_datos_mercado",
        "description": "Obtiene datos históricos de precio para un activo financiero.",
        "input_schema": {
            "type": "object",
            "properties": {
                "simbolo": {
                    "type": "string",
                    "description": "Símbolo del activo (e.g., AAPL, BTC, SPY)",
                },
                "dias": {
                    "type": "integer",
                    "description": "Número de días de historial a obtener (1–90)",
                },
            },
            "required": ["simbolo", "dias"],
        },
    },
    {
        "name": "calcular_metricas",
        "description": (
            "Calcula métricas financieras clave a partir de una serie de precios: "
            "rendimiento total, volatilidad anualizada y RSI (14 períodos)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "precios": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Lista de precios históricos en orden cronológico",
                },
                "simbolo": {
                    "type": "string",
                    "description": "Nombre del activo para incluir en el resultado",
                },
            },
            "required": ["precios", "simbolo"],
        },
    },
]

_PRECIO_BASE: dict[str, float] = {
    "BTC": 65000, "ETH": 3500, "SPY": 520,
    "AAPL": 185, "NVDA": 850, "TSLA": 200, "MSFT": 420,
}
_VOLATILIDAD: dict[str, float] = {
    "BTC": 0.04, "ETH": 0.035, "TSLA": 0.025,
    "NVDA": 0.02, "AAPL": 0.015, "MSFT": 0.012, "SPY": 0.01,
}


def _ejecutar_obtener_datos_mercado(simbolo: str, dias: int) -> dict[str, Any]:
    rng = random.Random(hash(simbolo) + datetime.now().toordinal())
    base = _PRECIO_BASE.get(simbolo, 100)
    vol = _VOLATILIDAD.get(simbolo, 0.02)

    precio = base * rng.uniform(0.88, 1.12)
    precios: list[float] = []
    for _ in range(max(1, dias)):
        precio *= 1 + rng.gauss(0, vol)
        precios.append(round(precio, 2))

    return {
        "simbolo": simbolo,
        "dias": dias,
        "precio_actual": precios[-1],
        "precio_inicial": precios[0],
        "maximo": round(max(precios), 2),
        "minimo": round(min(precios), 2),
        "precios": precios,
        "fecha": datetime.now().strftime("%Y-%m-%d"),
    }


def _ejecutar_calcular_metricas(precios: list[float], simbolo: str) -> dict[str, Any]:
    if len(precios) < 2:
        return {"error": "Se necesitan al menos 2 precios para calcular métricas"}

    rendimientos = [
        (precios[i] - precios[i - 1]) / precios[i - 1]
        for i in range(1, len(precios))
    ]
    rendimiento_total = (precios[-1] - precios[0]) / precios[0] * 100
    media = sum(rendimientos) / len(rendimientos)
    varianza = sum((r - media) ** 2 for r in rendimientos) / len(rendimientos)
    volatilidad_anual = (varianza ** 0.5) * (252 ** 0.5) * 100

    rsi: float | None = None
    if len(rendimientos) >= 14:
        ultimos = rendimientos[-14:]
        avg_gain = sum(r for r in ultimos if r > 0) / 14
        avg_loss = sum(-r for r in ultimos if r < 0) / 14
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = round(100 - (100 / (1 + rs)), 1)

    if rsi is not None:
        senal = "sobrecomprado" if rsi > 70 else "sobrevendido" if rsi < 30 else "neutral"
    else:
        senal = "insuficientes datos"

    return {
        "simbolo": simbolo,
        "rendimiento_total_pct": round(rendimiento_total, 2),
        "volatilidad_anualizada_pct": round(volatilidad_anual, 2),
        "rsi_14": rsi,
        "precio_inicial": precios[0],
        "precio_final": precios[-1],
        "señal_rsi": senal,
    }


def _ejecutar_herramienta(nombre: str, argumentos: dict) -> str:
    try:
        if nombre == "obtener_datos_mercado":
            resultado = _ejecutar_obtener_datos_mercado(**argumentos)
        elif nombre == "calcular_metricas":
            resultado = _ejecutar_calcular_metricas(**argumentos)
        else:
            resultado = {"error": f"Herramienta desconocida: {nombre}"}
    except Exception as exc:
        resultado = {"error": str(exc)}
    return json.dumps(resultado, ensure_ascii=False)


class AgenteFinanciero(AgenteBase):
    def __init__(self):
        super().__init__("AgenteFinanciero")
        self._cliente: anthropic.AsyncAnthropic | None = None
        self._activo = False

    async def inicializar(self):
        self._cliente = anthropic.AsyncAnthropic()
        logger.debug(f"{self.nombre}: cliente Anthropic listo")

    async def ejecutar(self):
        self._activo = True
        while self._activo:
            try:
                await self._ciclo_analisis()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"{self.nombre}: error en ciclo de análisis: {exc}")
            await asyncio.sleep(30)

    async def _ciclo_analisis(self):
        simbolo = random.choice(PORTAFOLIO)
        logger.info(f"{self.nombre}: analizando {simbolo}...")

        mensajes: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"Analiza el activo {simbolo} con historial de 30 días. "
                    "Obtén los datos de mercado, calcula las métricas y emite "
                    "tu evaluación con recomendación de inversión."
                ),
            }
        ]

        metricas_guardadas: dict = {}

        while True:
            async with self._cliente.messages.stream(
                model="claude-opus-4-7",
                max_tokens=1024,
                thinking={"type": "adaptive"},
                system=[
                    {
                        "type": "text",
                        "text": SISTEMA,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=HERRAMIENTAS,
                messages=mensajes,
            ) as stream:
                respuesta = await stream.get_final_message()

            tool_uses = [b for b in respuesta.content if b.type == "tool_use"]

            if respuesta.stop_reason == "end_turn" or not tool_uses:
                texto = next(
                    (b.text for b in respuesta.content if b.type == "text"), ""
                )
                if texto:
                    logger.info(f"{self.nombre} [{simbolo}]: {texto.strip()}")
                    await guardar_inversion({
                        "simbolo": simbolo,
                        "rendimiento_pct": metricas_guardadas.get("rendimiento_total_pct"),
                        "volatilidad_pct": metricas_guardadas.get("volatilidad_anualizada_pct"),
                        "rsi": metricas_guardadas.get("rsi_14"),
                        "senal": metricas_guardadas.get("señal_rsi"),
                        "analisis": texto.strip(),
                    })
                break

            mensajes.append({"role": "assistant", "content": respuesta.content})
            resultados = []
            for tu in tool_uses:
                resultado_json = _ejecutar_herramienta(tu.name, tu.input)
                resultados.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": resultado_json,
                })
                if tu.name == "calcular_metricas":
                    try:
                        metricas_guardadas = json.loads(resultado_json)
                    except Exception:
                        pass
            mensajes.append({"role": "user", "content": resultados})
            logger.debug(
                f"{self.nombre}: ejecutadas {len(tool_uses)} herramientas, "
                "continuando análisis..."
            )

    async def detener(self):
        self._activo = False
        logger.debug(f"{self.nombre}: recursos liberados")
