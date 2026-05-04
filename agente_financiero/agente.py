import asyncio
import json
import random
from datetime import datetime
from typing import Any

import anthropic
from loguru import logger

from base_datos.repositorios import guardar_inversion, obtener_analisis_previos
from nucleo.agente_base import AgenteBase
from agente_financiero.datos_mercado import obtener_precios_reales


SISTEMA = """Eres un agente financiero experto especializado en análisis técnico y gestión de riesgo.

Contexto operativo:
- Horizonte temporal: swing trading (1–2 semanas)
- Renta variable (AAPL, NVDA, TSLA, MSFT, SPY): tolerancia moderada al riesgo
- Criptomonedas (BTC, ETH): alta volatilidad esperada, umbral de riesgo más amplio

Proceso de análisis:
1. Consulta el historial previo del activo con `obtener_analisis_previos`.
2. Obtén datos históricos del activo con `obtener_datos_mercado` (60 días).
3. Calcula métricas financieras con `calcular_metricas`.
4. Emite tu evaluación con este formato exacto:

**Señales**: [RSI-14, MACD (línea/señal/histograma) y Bollinger Bands (%B y señal)]
**Contexto**: [rendimiento reciente y volatilidad observada vs. histórica del activo]
**Riesgo**: [BAJO / MEDIO / ALTO — justifica en una frase]
**Recomendación**: [COMPRAR / MANTENER / VENDER] — Confianza: [alta / media / baja]

Regla: si la volatilidad observada supera el doble de la típica del activo, eleva el riesgo \
un nivel y reduce la confianza de la recomendación."""

PORTAFOLIO = ["BTC", "ETH", "SPY", "AAPL", "NVDA", "TSLA", "MSFT"]

HERRAMIENTAS = [
    {
        "name": "obtener_analisis_previos",
        "description": (
            "Consulta los últimos análisis guardados para un activo en la base de datos. "
            "Úsalo primero para detectar persistencia de señales o tendencias recientes "
            "del mismo símbolo antes de calcular métricas nuevas."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "simbolo": {
                    "type": "string",
                    "description": "Símbolo del activo (e.g., AAPL, BTC, SPY)",
                },
                "limite": {
                    "type": "integer",
                    "description": "Número de análisis previos a recuperar (1–10, default 5)",
                },
            },
            "required": ["simbolo"],
        },
    },
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
            "Calcula métricas financieras a partir de una serie de precios: "
            "rendimiento total, volatilidad anualizada (varianza muestral), RSI-14 "
            "(suavizado de Wilder), MACD (EMA12-EMA26 con señal EMA9) y "
            "Bollinger Bands (SMA20 ± 2σ). Requiere al menos 60 precios para MACD completo."
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


def _simular_precios(simbolo: str, dias: int) -> list[float]:
    rng = random.Random(hash(simbolo) + datetime.now().toordinal())
    base = _PRECIO_BASE.get(simbolo, 100)
    vol = _VOLATILIDAD.get(simbolo, 0.02)
    precio = base * rng.uniform(0.88, 1.12)
    precios: list[float] = []
    for _ in range(max(1, dias)):
        precio *= 1 + rng.gauss(0, vol)
        precios.append(round(precio, 2))
    return precios


def _ema(valores: list[float], periodo: int) -> list[float]:
    """EMA estándar: semilla = SMA de los primeros `periodo` valores, k = 2/(periodo+1)."""
    if len(valores) < periodo:
        return []
    k = 2.0 / (periodo + 1)
    ema_val = sum(valores[:periodo]) / periodo
    resultado = [ema_val]
    for v in valores[periodo:]:
        ema_val = v * k + ema_val * (1 - k)
        resultado.append(ema_val)
    return resultado


def _calcular_macd(precios: list[float]) -> dict[str, Any] | None:
    ema12 = _ema(precios, 12)
    ema26 = _ema(precios, 26)
    if not ema26:
        return None

    # ema12[i + offset] y ema26[i] cubren el mismo extremo derecho de la ventana
    offset = 26 - 12
    linea_macd = [ema12[i + offset] - ema26[i] for i in range(len(ema26))]
    linea_signal = _ema(linea_macd, 9)

    macd_actual = round(linea_macd[-1], 4)
    res: dict[str, Any] = {"macd": macd_actual}

    if linea_signal:
        signal_actual = round(linea_signal[-1], 4)
        histograma = round(macd_actual - signal_actual, 4)
        senal = "alcista" if histograma > 0 else "bajista"
        if len(linea_macd) >= 2 and len(linea_signal) >= 2:
            hist_prev = linea_macd[-2] - linea_signal[-2]
            if hist_prev < 0 and histograma > 0:
                senal = "cruce_alcista"
            elif hist_prev > 0 and histograma < 0:
                senal = "cruce_bajista"
        res.update({"signal": signal_actual, "histograma": histograma, "senal_macd": senal})
    else:
        res["senal_macd"] = "señal_insuficiente"

    return res


def _calcular_bollinger(precios: list[float], periodo: int = 20) -> dict[str, Any] | None:
    if len(precios) < periodo:
        return None

    ventana = precios[-periodo:]
    sma = sum(ventana) / periodo
    std = (sum((p - sma) ** 2 for p in ventana) / (periodo - 1)) ** 0.5
    upper = round(sma + 2 * std, 2)
    lower = round(sma - 2 * std, 2)
    sma_r = round(sma, 2)
    ancho_pct = round((upper - lower) / sma_r * 100, 2) if sma_r else 0

    pct_b = (precios[-1] - lower) / (upper - lower) if upper != lower else 0.5
    if pct_b > 0.8:
        senal_bb = "cerca_banda_superior"
    elif pct_b < 0.2:
        senal_bb = "cerca_banda_inferior"
    else:
        senal_bb = "zona_media"

    return {
        "banda_superior": upper,
        "banda_media": sma_r,
        "banda_inferior": lower,
        "ancho_bandas_pct": ancho_pct,
        "pct_b": round(pct_b, 3),
        "senal_bb": senal_bb,
    }


async def _ejecutar_obtener_datos_mercado(simbolo: str, dias: int) -> dict[str, Any]:
    precios = await obtener_precios_reales(simbolo, dias)
    if precios:
        fuente = "real"
        logger.info(f"Datos reales obtenidos para {simbolo} ({len(precios)} días)")
    else:
        fuente = "simulado"
        precios = _simular_precios(simbolo, dias)
        logger.warning(f"APIs no disponibles para {simbolo}, usando datos simulados")

    return {
        "simbolo": simbolo,
        "dias": len(precios),
        "precio_actual": round(precios[-1], 2),
        "precio_inicial": round(precios[0], 2),
        "maximo": round(max(precios), 2),
        "minimo": round(min(precios), 2),
        "precios": precios,
        "fecha": datetime.now().strftime("%Y-%m-%d"),
        "fuente": fuente,
    }


def _ejecutar_calcular_metricas(precios: list[float], simbolo: str) -> dict[str, Any]:
    if len(precios) < 3:
        return {"error": "Se necesitan al menos 3 precios para calcular métricas"}

    rendimientos = [
        (precios[i] - precios[i - 1]) / precios[i - 1]
        for i in range(1, len(precios))
    ]
    n = len(rendimientos)
    rendimiento_total = (precios[-1] - precios[0]) / precios[0] * 100
    media = sum(rendimientos) / n
    # Varianza muestral (Bessel's correction: N-1) — convención estándar en finanzas
    varianza = sum((r - media) ** 2 for r in rendimientos) / (n - 1)
    volatilidad_anual = (varianza ** 0.5) * (252 ** 0.5) * 100

    rsi: float | None = None
    if n >= 14:
        # RSI con suavizado de Wilder: promedio inicial en los primeros 14 periodos,
        # luego EMA con alpha=1/14 para el resto. Más preciso que el promedio simple.
        avg_gain = sum(r for r in rendimientos[:14] if r > 0) / 14
        avg_loss = sum(-r for r in rendimientos[:14] if r < 0) / 14
        for r in rendimientos[14:]:
            gain = r if r > 0 else 0.0
            loss = -r if r < 0 else 0.0
            avg_gain = (avg_gain * 13 + gain) / 14
            avg_loss = (avg_loss * 13 + loss) / 14
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = round(100 - (100 / (1 + rs)), 1)

    if rsi is not None:
        senal = "sobrecomprado" if rsi > 70 else "sobrevendido" if rsi < 30 else "neutral"
    else:
        senal = "insuficientes datos"

    resultado: dict[str, Any] = {
        "simbolo": simbolo,
        "rendimiento_total_pct": round(rendimiento_total, 2),
        "volatilidad_anualizada_pct": round(volatilidad_anual, 2),
        "rsi_14": rsi,
        "precio_inicial": precios[0],
        "precio_final": precios[-1],
        "señal_rsi": senal,
    }

    macd = _calcular_macd(precios)
    if macd:
        resultado["macd"] = macd

    bb = _calcular_bollinger(precios)
    if bb:
        resultado["bollinger"] = bb

    return resultado


async def _ejecutar_herramienta(nombre: str, argumentos: dict) -> str:
    try:
        if nombre == "obtener_analisis_previos":
            resultado = await obtener_analisis_previos(**argumentos)
        elif nombre == "obtener_datos_mercado":
            resultado = await _ejecutar_obtener_datos_mercado(**argumentos)
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
                    f"Analiza el activo {simbolo} con historial de 60 días. "
                    "Obtén los datos de mercado, calcula las métricas y emite "
                    "tu evaluación con recomendación de inversión."
                ),
            }
        ]

        metricas_guardadas: dict = {}
        fuente_datos = "simulado"

        while True:
            async with self._cliente.messages.stream(
                model="claude-opus-4-7",
                max_tokens=1536,
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
                        "fuente": fuente_datos,
                    })
                break

            mensajes.append({"role": "assistant", "content": respuesta.content})
            resultados = []
            for tu in tool_uses:
                resultado_json = await _ejecutar_herramienta(tu.name, tu.input)
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
                elif tu.name == "obtener_datos_mercado":
                    try:
                        fuente_datos = json.loads(resultado_json).get("fuente", "simulado")
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
