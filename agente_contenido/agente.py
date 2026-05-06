import asyncio
import json
import random
from datetime import datetime
from typing import Any

import anthropic
from loguru import logger

from base_datos.repositorios import guardar_contenido
from nucleo.agente_base import AgenteBase


SISTEMA = """Eres un agente experto en marketing de contenido digital. Tu función es
identificar tendencias relevantes, evaluar el potencial de engagement y crear briefs
de contenido de alto impacto para distintas plataformas digitales.

Proceso de trabajo:
1. Obtén las tendencias actuales para la plataforma y categoría con `obtener_tendencias`.
2. Evalúa el potencial del tema elegido con `evaluar_contenido`.
3. Redacta un brief de contenido (máximo 5 oraciones) con: tema seleccionado,
   formato recomendado, hook principal, audiencia objetivo y llamada a la acción."""

PLATAFORMAS = ["Instagram", "LinkedIn", "YouTube", "TikTok", "Blog"]

CATEGORIAS_POR_PLATAFORMA: dict[str, list[str]] = {
    "Instagram":  ["lifestyle", "fitness", "gastronomia", "viajes", "moda"],
    "LinkedIn":   ["tecnologia", "liderazgo", "emprendimiento", "productividad", "ia"],
    "YouTube":    ["tutoriales", "entretenimiento", "educacion", "gaming", "finanzas"],
    "TikTok":     ["humor", "baile", "tips-rapidos", "recetas", "tendencias"],
    "Blog":       ["seo", "tecnologia", "finanzas-personales", "salud", "educacion"],
}

TENDENCIAS_BASE: dict[str, list[str]] = {
    "lifestyle":          ["minimalismo digital", "slow living", "bienestar holistico"],
    "fitness":            ["entrenamiento en 15 min", "pilates reformer", "calistenia avanzada"],
    "gastronomia":        ["cocina fermentada", "proteina vegetal", "recetas de 5 ingredientes"],
    "viajes":             ["turismo regenerativo", "nómada digital", "viajes en tren"],
    "moda":               ["moda circular", "cápsula wardrobe", "tendencias Y2K"],
    "tecnologia":         ["IA generativa en empresas", "ciberseguridad personal", "no-code tools"],
    "liderazgo":          ["liderazgo empático", "equipos remotos", "inteligencia emocional"],
    "emprendimiento":     ["bootstrapping", "solopreneurs", "validación de ideas"],
    "productividad":      ["sistema PARA", "time blocking", "deep work"],
    "ia":                 ["prompts avanzados", "agentes autónomos", "IA en marketing"],
    "tutoriales":         ["edición de video", "programación para no-devs", "diseño con IA"],
    "entretenimiento":    ["docuseries", "true crime", "vlogs de viaje"],
    "educacion":          ["microlearning", "aprendizaje activo", "certificaciones online"],
    "gaming":             ["speedruns", "gaming retro", "esports análisis"],
    "finanzas":           ["inversión pasiva", "FIRE movement", "criptomonedas 2025"],
    "humor":              ["parodias de oficina", "situaciones cotidianas", "memes interactivos"],
    "baile":              ["coreografías virales", "fusión de géneros", "duetos"],
    "tips-rapidos":       ["hacks de productividad", "trucos de cocina", "vida saludable"],
    "recetas":            ["bowls nutritivos", "postres sin horno", "snacks proteicos"],
    "tendencias":         ["aesthetics 2025", "micro-tendencias", "revival años 90"],
    "seo":                ["SEO semántico", "búsqueda por voz", "contenido EEAT"],
    "finanzas-personales": ["presupuesto cero", "fondos índice", "planificación fiscal"],
    "salud":              ["longevidad", "microbioma intestinal", "sueño de calidad"],
}

FORMATOS_POR_PLATAFORMA: dict[str, list[str]] = {
    "Instagram":  ["carrusel 10 slides", "Reel 30 s", "historia interactiva"],
    "LinkedIn":   ["artículo de opinión", "post con lista", "caso de estudio"],
    "YouTube":    ["video tutorial 10 min", "short 60 s", "documental corto"],
    "TikTok":     ["video 15 s con hook", "dueto", "stitch + comentario"],
    "Blog":       ["guía definitiva 2000 palabras", "listicle SEO", "caso práctico"],
}

HERRAMIENTAS = [
    {
        "name": "obtener_tendencias",
        "description": "Obtiene temas en tendencia para una plataforma y categoría específicas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plataforma": {
                    "type": "string",
                    "description": "Plataforma digital (Instagram, LinkedIn, YouTube, TikTok, Blog)",
                },
                "categoria": {
                    "type": "string",
                    "description": "Categoría de contenido dentro de la plataforma",
                },
            },
            "required": ["plataforma", "categoria"],
        },
    },
    {
        "name": "evaluar_contenido",
        "description": (
            "Evalúa el potencial de un tema de contenido: estima alcance, "
            "tasa de engagement y dificultad de producción."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tema": {
                    "type": "string",
                    "description": "Tema o título del contenido a evaluar",
                },
                "plataforma": {
                    "type": "string",
                    "description": "Plataforma donde se publicará el contenido",
                },
                "formato": {
                    "type": "string",
                    "description": "Formato del contenido (video, carrusel, artículo, etc.)",
                },
            },
            "required": ["tema", "plataforma", "formato"],
        },
    },
]


def _ejecutar_obtener_tendencias(plataforma: str, categoria: str) -> dict[str, Any]:
    temas = TENDENCIAS_BASE.get(categoria, ["contenido evergreen", "behind the scenes"])
    formatos = FORMATOS_POR_PLATAFORMA.get(plataforma, ["post estándar"])

    rng = random.Random(hash(plataforma + categoria) + datetime.now().toordinal())
    temas_ordenados = rng.sample(temas, min(3, len(temas)))

    return {
        "plataforma": plataforma,
        "categoria": categoria,
        "temas_trending": temas_ordenados,
        "formatos_recomendados": formatos,
        "nivel_competencia": rng.choice(["bajo", "medio", "alto"]),
        "mejor_horario": rng.choice(["08:00–10:00", "12:00–14:00", "18:00–21:00"]),
        "fecha": datetime.now().strftime("%Y-%m-%d"),
    }


def _ejecutar_evaluar_contenido(
    tema: str, plataforma: str, formato: str
) -> dict[str, Any]:
    rng = random.Random(hash(tema + plataforma) + datetime.now().toordinal())

    alcance_base = {
        "Instagram": 5000, "TikTok": 20000, "YouTube": 3000,
        "LinkedIn": 8000, "Blog": 1500,
    }
    base = alcance_base.get(plataforma, 3000)
    alcance_estimado = int(base * rng.uniform(0.6, 2.5))
    engagement_pct = round(rng.uniform(1.5, 8.5), 1)
    dificultad = rng.choice(["baja", "media", "alta"])
    tiempo_prod = {"baja": "1–2 h", "media": "3–5 h", "alta": "6–10 h"}[dificultad]

    puntuacion = round(
        (alcance_estimado / base) * 40
        + engagement_pct * 5
        + (3 if dificultad == "baja" else 1 if dificultad == "media" else 0) * 5,
        1,
    )

    return {
        "tema": tema,
        "plataforma": plataforma,
        "formato": formato,
        "alcance_estimado": alcance_estimado,
        "engagement_estimado_pct": engagement_pct,
        "dificultad_produccion": dificultad,
        "tiempo_produccion_estimado": tiempo_prod,
        "puntuacion_potencial": min(puntuacion, 100.0),
        "recomendado": puntuacion >= 40,
    }


def _ejecutar_herramienta(nombre: str, argumentos: dict) -> str:
    try:
        if nombre == "obtener_tendencias":
            resultado = _ejecutar_obtener_tendencias(**argumentos)
        elif nombre == "evaluar_contenido":
            resultado = _ejecutar_evaluar_contenido(**argumentos)
        else:
            resultado = {"error": f"Herramienta desconocida: {nombre}"}
    except Exception as exc:
        resultado = {"error": str(exc)}
    return json.dumps(resultado, ensure_ascii=False)


class AgenteContenido(AgenteBase):
    def __init__(self):
        super().__init__("AgenteContenido")
        self._cliente: anthropic.AsyncAnthropic | None = None
        self._activo = False

    async def inicializar(self):
        self._cliente = anthropic.AsyncAnthropic()
        logger.debug(f"{self.nombre}: cliente Anthropic listo")

    async def ejecutar(self):
        self._activo = True
        self.estado = "esperando"
        while self._activo:
            try:
                await self._ciclo_analisis()
                self._marcar_fin_ok()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._marcar_error(exc)
                logger.error(f"{self.nombre}: error en ciclo de análisis: {exc}")
            await asyncio.sleep(45)
        self.estado = "detenido"

    async def _ciclo_analisis(self):
        plataforma = random.choice(PLATAFORMAS)
        categoria = random.choice(CATEGORIAS_POR_PLATAFORMA[plataforma])
        self._marcar_inicio(f"{plataforma} / {categoria}")
        logger.info(f"{self.nombre}: analizando {plataforma} / {categoria}...")

        mensajes: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"Analiza oportunidades de contenido para la plataforma {plataforma} "
                    f"en la categoría '{categoria}'. Identifica el tema con mayor potencial, "
                    "evalúa su alcance y engagement estimados, y crea un brief de contenido."
                ),
            }
        ]

        mejor_evaluacion: dict = {}

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
                    logger.info(
                        f"{self.nombre} [{plataforma}/{categoria}]: {texto.strip()}"
                    )
                    await guardar_contenido({
                        "plataforma": plataforma,
                        "categoria": categoria,
                        "tema": mejor_evaluacion.get("tema"),
                        "formato": mejor_evaluacion.get("formato"),
                        "alcance_estimado": mejor_evaluacion.get("alcance_estimado"),
                        "engagement_pct": mejor_evaluacion.get("engagement_estimado_pct"),
                        "brief": texto.strip(),
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
                if tu.name == "evaluar_contenido":
                    try:
                        eval_data = json.loads(resultado_json)
                        puntuacion = eval_data.get("puntuacion_potencial", 0)
                        if puntuacion > mejor_evaluacion.get("puntuacion_potencial", -1):
                            mejor_evaluacion = eval_data
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
