# agente_financiero/agente_digestor.py
import ollama
from datetime import datetime

def consolidar_reportes(
    reporte_noticias: str = "",
    reporte_sentimiento: str = "",
    reporte_macro: str = "",
    reporte_historico: str = "",
    reporte_fundamental: str = "",
    reporte_youtube: str = "",
) -> dict:

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    contexto = f"""
FECHA Y HORA: {timestamp}

=== NOTICIAS FINANCIERAS ===
{reporte_noticias or 'Sin datos'}

=== SENTIMIENTO DE MERCADO ===
{reporte_sentimiento or 'Sin datos'}

=== CONTEXTO MACRO Y GEOPOLITICO ===
{reporte_macro or 'Sin datos'}

=== ANALISIS HISTORICO Y PATRONES ===
{reporte_historico or 'Sin datos'}

=== ANALISIS FUNDAMENTAL ===
{reporte_fundamental or 'Sin datos'}

=== ANALISIS DE VIDEOS YOUTUBE ===
{reporte_youtube or 'Sin datos'}
"""

    print("[agente_digestor] Consolidando todos los reportes...")
    respuesta = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "system",
                "content": "Eres un digestor de inteligencia financiera. Recibes reportes de multiples sub-agentes y los consolidas en un reporte ejecutivo estructurado para el agente financiero principal. El reporte debe ser claro, accionable y priorizado. Responde en espanol."
            },
            {
                "role": "user",
                "content": "Consolida estos reportes en un reporte ejecutivo:\n" + contexto
            }
        ]
    )

    reporte_consolidado = respuesta["message"]["content"]

    print("[agente_digestor] Generando decision final...")
    decision = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "system",
                "content": "Eres el agente financiero principal. Basandote en el reporte ejecutivo, toma una decision de inversion clara. Formato: ACCION (COMPRAR/VENDER/MANTENER), SIMBOLO, RAZON (1 oracion), CONFIANZA (1-10), HORIZONTE (dias/semanas). Maximo 5 decisiones. Responde en espanol."
            },
            {
                "role": "user",
                "content": "Basandote en este reporte, toma decisiones de inversion:\n" + reporte_consolidado
            }
        ]
    )

    return {
        "timestamp": timestamp,
        "reporte_consolidado": reporte_consolidado,
        "decisiones": decision["message"]["content"],
        "modelo": "llama3.2"
    }


def ejecutar_ciclo_completo() -> dict:
    from agente_financiero.noticias_web import obtener_noticias_mercado
    from agente_financiero.agente_sentimiento import obtener_reporte_sentimiento
    from agente_financiero.agente_macro import obtener_reporte_macro
    from agente_financiero.agente_historico import obtener_reporte_historico
    from agente_financiero.agente_fundamental import obtener_reporte_fundamental

    print("\n=== INICIANDO CICLO COMPLETO DE ANALISIS ===\n")

    print("[1/5] Noticias financieras...")
    noticias = obtener_noticias_mercado()

    print("[2/5] Sentimiento de mercado...")
    sentimiento = obtener_reporte_sentimiento()

    print("[3/5] Contexto macro...")
    macro = obtener_reporte_macro()

    print("[4/5] Analisis historico...")
    historico = obtener_reporte_historico()

    print("[5/5] Analisis fundamental...")
    fundamental = obtener_reporte_fundamental()

    print("\n[DIGESTOR] Consolidando todo...")
    resultado = consolidar_reportes(
        reporte_noticias=noticias,
        reporte_sentimiento=sentimiento,
        reporte_macro=macro,
        reporte_historico=historico,
        reporte_fundamental=fundamental,
    )

    print("\n=== REPORTE EJECUTIVO ===")
    print(resultado["reporte_consolidado"])
    print("\n=== DECISIONES DE INVERSION ===")
    print(resultado["decisiones"])

    return resultado