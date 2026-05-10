# agente_financiero/agente_youtube.py
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
from nucleo.cliente_ia import chat

VIDEOS_SEGUIMIENTO = [
    "fvGLnthJDsg",
    "phSFh9Gw4nE",
    "mJPBRjMCBSk",
]

def extraer_transcripcion(video_id: str) -> str:
    try:
        ytt = YouTubeTranscriptApi()
        transcript = ytt.fetch(video_id)
        return " ".join([t.text for t in transcript])
    except TranscriptsDisabled:
        return "Video sin transcripción"
    except NoTranscriptFound:
        return "Sin transcripción disponible"
    except Exception as e:
        return f"Error: {e}"

async def analizar_video_financiero(video_id: str, titulo: str = "") -> dict:
    print(f"[agente_youtube] Extrayendo {video_id}...")
    transcripcion = extraer_transcripcion(video_id)

    if transcripcion.startswith("Error") or transcripcion.startswith("Video") or transcripcion.startswith("Sin"):
        return {"video_id": video_id, "error": transcripcion, "analisis": None}

    print(f"[agente_youtube] Analizando con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"Analiza este video financiero:\n\nTítulo: {titulo}\n\nTranscripción:\n{transcripcion[:3000]}"}],
        system="""Eres un analista financiero experto.
Analiza transcripciones de videos financieros y extrae:
1. Activos mencionados (acciones, crypto, ETFs)
2. Tendencia recomendada (alcista/bajista/neutral)
3. Razones principales
4. Nivel de confianza (alto/medio/bajo)
5. Horizonte temporal mencionado
Responde siempre en español de forma concisa.""",
        max_tokens=800
    )

    return {
        "video_id": video_id,
        "titulo": titulo,
        "transcripcion_chars": len(transcripcion),
        "analisis": respuesta["texto"],
        "modelo": respuesta["modelo"]
    }

async def obtener_reporte_youtube(video_ids: list = None) -> str:
    if video_ids is None:
        video_ids = VIDEOS_SEGUIMIENTO
    reportes = []
    for vid in video_ids:
        resultado = await analizar_video_financiero(vid)
        if resultado.get("analisis"):
            reportes.append(f"VIDEO {vid}:\n{resultado['analisis']}")

    if not reportes:
        return "No se pudieron analizar videos"

    resumen = await chat(
        mensajes=[{"role": "user", "content": f"Consolida estos análisis de videos financieros en un reporte ejecutivo:\n\n{'---'.join(reportes)}"}],
        system="Eres un digestor de información financiera. Consolida múltiples análisis en un reporte ejecutivo conciso. Responde en español.",
        max_tokens=600
    )
    return resumen["texto"]