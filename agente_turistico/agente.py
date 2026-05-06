import asyncio
import json
import random
from datetime import datetime
from typing import Any

import anthropic
from loguru import logger

from base_datos.repositorios import guardar_noticia
from nucleo.agente_base import AgenteBase


SISTEMA = """Eres un agente experto en planificación de viajes y turismo. Tu función es
analizar destinos, evaluar su atractivo según la temporada y el presupuesto disponible,
y crear recomendaciones de viaje personalizadas y accionables.

Proceso de trabajo:
1. Obtén información detallada del destino con `obtener_info_destino`.
2. Genera un itinerario optimizado con `planificar_itinerario`.
3. Redacta una recomendación de viaje concisa (máximo 5 oraciones) con: mejor época
   para visitar, actividades imperdibles, presupuesto estimado diario y el consejo
   más valioso para ese destino."""

DESTINOS = [
    "Tokyo", "Barcelona", "Nueva York", "Ciudad de México",
    "Bali", "París", "Dubái", "Buenos Aires", "Bangkok", "Lisboa",
]

PRESUPUESTOS = ["económico", "moderado", "premium"]

_INFO_DESTINOS: dict[str, dict[str, Any]] = {
    "Tokyo": {
        "pais": "Japón", "idioma": "Japonés",
        "mejor_epoca": ["marzo-abril (sakura)", "octubre-noviembre (otoño)"],
        "clima_actual": "templado",
        "costo_diario_usd": {"económico": 80, "moderado": 150, "premium": 320},
        "atracciones": ["Shibuya Crossing", "Templo Senso-ji", "Akihabara", "Monte Fuji", "Harajuku"],
        "gastronomia": ["ramen", "sushi omakase", "izakaya", "tempura", "wagyu"],
        "consejo": "Compra el IC Card para transporte público; evita el rush hour en metro.",
        "visado": "libre para muchos países hasta 90 días",
    },
    "Barcelona": {
        "pais": "España", "idioma": "Español / Catalán",
        "mejor_epoca": ["mayo-junio", "septiembre-octubre"],
        "clima_actual": "mediterráneo cálido",
        "costo_diario_usd": {"económico": 70, "moderado": 130, "premium": 280},
        "atracciones": ["Sagrada Família", "Park Güell", "Las Ramblas", "Barrio Gótico", "Camp Nou"],
        "gastronomia": ["tapas", "paella", "pan con tomate", "croquetas", "crema catalana"],
        "consejo": "Reserva la Sagrada Família con meses de anticipación; el turismo es masivo en verano.",
        "visado": "Schengen",
    },
    "Nueva York": {
        "pais": "EE.UU.", "idioma": "Inglés",
        "mejor_epoca": ["abril-junio", "septiembre-noviembre"],
        "clima_actual": "continental",
        "costo_diario_usd": {"económico": 120, "moderado": 220, "premium": 500},
        "atracciones": ["Central Park", "Times Square", "Metropolitan Museum", "Brooklyn Bridge", "High Line"],
        "gastronomia": ["bagel con salmón", "pizza NY", "hot dog", "cheesecake", "brunch"],
        "consejo": "Usa el metro en lugar de taxis; pasa por Staten Island Ferry gratis para ver la Estatua de la Libertad.",
        "visado": "ESTA requerida",
    },
    "Ciudad de México": {
        "pais": "México", "idioma": "Español",
        "mejor_epoca": ["marzo-mayo", "octubre-diciembre"],
        "clima_actual": "subtropical de altura",
        "costo_diario_usd": {"económico": 40, "moderado": 80, "premium": 180},
        "atracciones": ["Teotihuacán", "Zócalo", "Xochimilco", "Museo Frida Kahlo", "Polanco"],
        "gastronomia": ["tacos al pastor", "tlayudas", "chiles en nogada", "tamales", "mezcal"],
        "consejo": "La altitud (2240 m) afecta los primeros días; hidrátate bien y toma el primer día con calma.",
        "visado": "libre para la mayoría",
    },
    "Bali": {
        "pais": "Indonesia", "idioma": "Balinés / Indonesio",
        "mejor_epoca": ["abril-octubre (temporada seca)"],
        "clima_actual": "tropical",
        "costo_diario_usd": {"económico": 35, "moderado": 75, "premium": 200},
        "atracciones": ["Templo Tanah Lot", "Ubud Rice Terraces", "Seminyak Beach", "Volcán Batur", "Uluwatu"],
        "gastronomia": ["nasi goreng", "satay", "babi guling", "mie goreng", "smoothie bowls"],
        "consejo": "Alquila una scooter en Ubud; es la forma más eficiente y barata de moverse.",
        "visado": "VOA (Visa on Arrival) disponible",
    },
    "París": {
        "pais": "Francia", "idioma": "Francés",
        "mejor_epoca": ["abril-junio", "septiembre-octubre"],
        "clima_actual": "oceánico",
        "costo_diario_usd": {"económico": 90, "moderado": 170, "premium": 400},
        "atracciones": ["Torre Eiffel", "Louvre", "Montmartre", "Musée d'Orsay", "Le Marais"],
        "gastronomia": ["croissant", "crêpes", "coq au vin", "boeuf bourguignon", "macarons"],
        "consejo": "Compra el Paris Museum Pass; ahorra dinero y evita filas en los principales museos.",
        "visado": "Schengen",
    },
    "Dubái": {
        "pais": "EAU", "idioma": "Árabe / Inglés",
        "mejor_epoca": ["noviembre-marzo (clima agradable)"],
        "clima_actual": "desértico árido",
        "costo_diario_usd": {"económico": 100, "moderado": 200, "premium": 600},
        "atracciones": ["Burj Khalifa", "Palm Jumeirah", "Dubai Mall", "Desierto Al Qudra", "Old Souk"],
        "gastronomia": ["shawarma", "hummus", "mandi", "luqaimat", "restaurantes Michelin"],
        "consejo": "El metro cubre las principales atracciones; evita taxis en hora pico.",
        "visado": "visa on arrival para muchos países",
    },
    "Buenos Aires": {
        "pais": "Argentina", "idioma": "Español",
        "mejor_epoca": ["septiembre-noviembre", "marzo-mayo"],
        "clima_actual": "templado húmedo",
        "costo_diario_usd": {"económico": 30, "moderado": 60, "premium": 140},
        "atracciones": ["La Boca", "Recoleta", "San Telmo", "Teatro Colón", "Puerto Madero"],
        "gastronomia": ["asado", "empanadas", "milanesa", "dulce de leche", "mate"],
        "consejo": "Cambia dinero en casas de cambio oficiales; la diferencia con el tipo oficial puede ser significativa.",
        "visado": "libre para la mayoría",
    },
    "Bangkok": {
        "pais": "Tailandia", "idioma": "Tailandés",
        "mejor_epoca": ["noviembre-febrero (temporada seca y fresca)"],
        "clima_actual": "tropical monzónico",
        "costo_diario_usd": {"económico": 30, "moderado": 65, "premium": 180},
        "atracciones": ["Gran Palacio", "Wat Pho", "Chatuchak Market", "Khao San Road", "Chao Phraya"],
        "gastronomia": ["pad thai", "tom yum", "mango sticky rice", "som tum", "street food"],
        "consejo": "Usa el BTS Skytrain para evitar el tráfico; negocia siempre el precio del tuk-tuk.",
        "visado": "libre hasta 30 días para muchos países",
    },
    "Lisboa": {
        "pais": "Portugal", "idioma": "Portugués",
        "mejor_epoca": ["marzo-mayo", "septiembre-octubre"],
        "clima_actual": "mediterráneo",
        "costo_diario_usd": {"económico": 55, "moderado": 100, "premium": 230},
        "atracciones": ["Torre de Belém", "Alfama", "Sintra", "LX Factory", "Pastéis de Belém"],
        "gastronomia": ["pastel de nata", "bacalhau", "sardinas asadas", "ginjinha", "bifanas"],
        "consejo": "El tram 28 es icónico pero lleno de turistas; intenta tomarlo muy temprano en la mañana.",
        "visado": "Schengen",
    },
}

_ACTIVIDADES: dict[str, dict[str, list[str]]] = {
    destino: {
        "mañana":  info["atracciones"][:2],
        "tarde":   info["atracciones"][2:4],
        "noche":   [f"Cena de {info['gastronomia'][0]}", f"Degustación de {info['gastronomia'][1]}"],
    }
    for destino, info in _INFO_DESTINOS.items()
}

HERRAMIENTAS = [
    {
        "name": "obtener_info_destino",
        "description": (
            "Obtiene información completa de un destino turístico: clima, atracciones "
            "principales, gastronomía, costo estimado por día y mejor época para visitar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "destino": {
                    "type": "string",
                    "description": "Ciudad o destino turístico (e.g., Tokyo, Barcelona, Bali)",
                },
                "presupuesto": {
                    "type": "string",
                    "enum": ["económico", "moderado", "premium"],
                    "description": "Nivel de presupuesto del viajero",
                },
            },
            "required": ["destino", "presupuesto"],
        },
    },
    {
        "name": "planificar_itinerario",
        "description": "Genera un itinerario día a día para un destino y duración de viaje dados.",
        "input_schema": {
            "type": "object",
            "properties": {
                "destino": {
                    "type": "string",
                    "description": "Ciudad o destino turístico",
                },
                "dias": {
                    "type": "integer",
                    "description": "Duración total del viaje en días (1–7)",
                },
            },
            "required": ["destino", "dias"],
        },
    },
]


def _ejecutar_obtener_info_destino(
    destino: str, presupuesto: str
) -> dict[str, Any]:
    info = _INFO_DESTINOS.get(destino)
    if not info:
        destinos_disponibles = list(_INFO_DESTINOS.keys())
        return {"error": f"Destino no encontrado. Disponibles: {destinos_disponibles}"}

    costo = info["costo_diario_usd"].get(presupuesto, info["costo_diario_usd"]["moderado"])
    return {
        "destino": destino,
        "pais": info["pais"],
        "idioma": info["idioma"],
        "mejor_epoca": info["mejor_epoca"],
        "clima_actual": info["clima_actual"],
        "costo_diario_usd": costo,
        "presupuesto_seleccionado": presupuesto,
        "top_atracciones": info["atracciones"],
        "gastronomia_recomendada": info["gastronomia"][:3],
        "consejo_clave": info["consejo"],
        "visado": info["visado"],
        "fecha_consulta": datetime.now().strftime("%Y-%m-%d"),
    }


def _ejecutar_planificar_itinerario(destino: str, dias: int) -> dict[str, Any]:
    dias = max(1, min(dias, 7))
    actividades = _ACTIVIDADES.get(destino)
    info = _INFO_DESTINOS.get(destino)

    if not actividades or not info:
        return {"error": f"No hay datos de itinerario para {destino}"}

    rng = random.Random(hash(destino) + datetime.now().toordinal())
    itinerario = {}
    atracciones_pool = list(info["atracciones"])
    gastronomia_pool = list(info["gastronomia"])
    rng.shuffle(atracciones_pool)
    rng.shuffle(gastronomia_pool)

    for dia in range(1, dias + 1):
        idx = (dia - 1) % len(atracciones_pool)
        itinerario[f"dia_{dia}"] = {
            "mañana": atracciones_pool[idx],
            "tarde": atracciones_pool[(idx + 1) % len(atracciones_pool)],
            "noche": f"Cena: {gastronomia_pool[dia % len(gastronomia_pool)]}",
        }

    return {
        "destino": destino,
        "duracion_dias": dias,
        "itinerario": itinerario,
        "nota": "Itinerario sugerido; ajusta según intereses personales.",
    }


def _ejecutar_herramienta(nombre: str, argumentos: dict) -> str:
    try:
        if nombre == "obtener_info_destino":
            resultado = _ejecutar_obtener_info_destino(**argumentos)
        elif nombre == "planificar_itinerario":
            resultado = _ejecutar_planificar_itinerario(**argumentos)
        else:
            resultado = {"error": f"Herramienta desconocida: {nombre}"}
    except Exception as exc:
        resultado = {"error": str(exc)}
    return json.dumps(resultado, ensure_ascii=False)


class AgenteTuristico(AgenteBase):
    def __init__(self):
        super().__init__("AgenteTuristico")
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
            await asyncio.sleep(60)
        self.estado = "detenido"

    async def _ciclo_analisis(self):
        destino = random.choice(DESTINOS)
        presupuesto = random.choice(PRESUPUESTOS)
        dias = random.randint(3, 7)
        self._marcar_inicio(f"{destino} ({dias}d, {presupuesto})")
        logger.info(f"{self.nombre}: planificando {destino} ({dias} días, {presupuesto})...")

        mensajes: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"Quiero planificar un viaje a {destino} de {dias} días "
                    f"con presupuesto {presupuesto}. Obtén la información del destino, "
                    "genera el itinerario y dame tu recomendación completa."
                ),
            }
        ]

        info_destino_guardada: dict = {}

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
                        f"{self.nombre} [{destino}/{presupuesto}]: {texto.strip()}"
                    )
                    mejor_epoca = info_destino_guardada.get("mejor_epoca")
                    await guardar_noticia({
                        "destino": destino,
                        "presupuesto": presupuesto,
                        "dias": dias,
                        "costo_diario_usd": info_destino_guardada.get("costo_diario_usd"),
                        "mejor_epoca": (
                            ", ".join(mejor_epoca) if isinstance(mejor_epoca, list) else mejor_epoca
                        ),
                        "recomendacion": texto.strip(),
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
                if tu.name == "obtener_info_destino":
                    try:
                        info_destino_guardada = json.loads(resultado_json)
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
