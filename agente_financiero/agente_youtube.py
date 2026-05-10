# agente_financiero/agente_youtube.py
import os
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
import ollama

# Canales financieros reconocidos para analizar
CANALES = {
    "benjamin_graham": [
        "https://www.youtube.com/@BenFelixCSI",
        "https://www.youtube.com/@TheSwedishInvestor",
    ],
    "crypto": [
        "https://www.youtube.com/@CoinBureau",
    ],
    "mercados": [
        "https://www.youtube.com/@PatrickBoyleinvestments",
    ]
}

# IDs de videos financieros para analizar automáticamente
VIDEOS_SEGUIMIENTO = [
    "dQw4w9WgXcQ",  # reemplaza con IDs reales de videos financieros
]

def extraer_transcripcion(video_id: str, idiomas: list = ["es", "en"]) -> str:
    try:
        ytt = YouTubeTranscriptApi()
        transcript = ytt.fetch(video_id)
        texto = " ".join([t.text for t in transcript])
        return texto
    except TranscriptsDisabled:
        return "Video sin transcripción disponible"
    except NoTranscriptFound:
        return "No se encontró transcripción en los idiomas solicitados"
    except Exception as e:
        return f"Error: {e}"

def analizar_video_financiero(video_id: str, titulo: str = "") -> dict:
    print(f"[agente_youtube] Extrayendo transcripción de {video_id}...")
    transcripcion = extraer_transcripcion(video_id)
    
    if transcripcion.startswith("Error") or transcripcion.startswith("Video") or transcripcion.startswith("No"):
        return {"video_id": video_id, "error": transcripcion, "analisis": None}
    
    # Limita a 3000 caracteres para no saturar Ollama
    texto_recortado = transcripcion[:3000]
    
    print(f"[agente_youtube] Analizando con Ollama...")
    respuesta = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "system",
                "content": """Eres un analista financiero experto. 
                Analiza transcripciones de videos financieros y extrae:
                1. Activos mencionados (acciones, crypto, ETFs)
                2. Tendencia recomendada (alcista/bajista/neutral)
                3. Razones principales
                4. Nivel de confianza (alto/medio/bajo)
                5. Horizonte temporal mencionado
                Responde siempre en español de forma concisa."""
            },
            {
                "role": "user",
                "content": f"Analiza este video financiero:\n\nTítulo: {titulo}\n\nTranscripción:\n{texto_recortado}"
            }
        ]
    )
    
    return {
        "video_id": video_id,
        "titulo": titulo,
        "transcripcion_chars": len(transcripcion),
        "analisis": respuesta["message"]["content"],
        "modelo": "llama3.2"
    }

def obtener_reporte_youtube(video_ids: list) -> str:
    reportes = []
    for vid in video_ids:
        resultado = analizar_video_financiero(vid)
        if resultado.get("analisis"):
            reportes.append(f"VIDEO {vid}:\n{resultado['analisis']}")
    
    if not reportes:
        return "No se pudieron analizar videos en este ciclo"
    
    # Digestor: consolida todos los análisis en un resumen
    resumen = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "system", 
                "content": "Eres un digestor de información financiera. Consolida múltiples análisis de videos en un reporte ejecutivo conciso con las señales más importantes. Responde en español."
            },
            {
                "role": "user",
                "content": f"Consolida estos análisis de videos financieros en un reporte ejecutivo:\n\n{'---'.join(reportes)}"
            }
        ]
    )
    
    return resumen["message"]["content"]