# agente_financiero/agente_digestor.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from nucleo.cliente_ia import chat

async def consolidar_reportes(
    reporte_noticias: str = "",
    reporte_sentimiento: str = "",
    reporte_macro: str = "",
    reporte_historico: str = "",
    reporte_fundamental: str = "",
    reporte_youtube: str = "",
) -> dict:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    contexto = f"""
FECHA: {timestamp}

=== NOTICIAS FINANCIERAS ===
{reporte_noticias or 'Sin datos'}

=== SENTIMIENTO DE MERCADO ===
{reporte_sentimiento or 'Sin datos'}

=== CONTEXTO MACRO Y GEOPOLITICO ===
{reporte_macro or 'Sin datos'}

=== ANALISIS HISTORICO ===
{reporte_historico or 'Sin datos'}

=== ANALISIS FUNDAMENTAL ===
{reporte_fundamental or 'Sin datos'}

=== VIDEOS YOUTUBE ===
{reporte_youtube or 'Sin datos'}
"""
    print("[agente_digestor] Consolidando reportes...")
    reporte = await chat(
        mensajes=[{"role": "user", "content": "Consolida estos reportes en un reporte ejecutivo:\n" + contexto}],
        system="Eres un digestor de inteligencia financiera. Consolida reportes de múltiples sub-agentes en un reporte ejecutivo claro, priorizado y accionable. Identifica las mejores oportunidades de inversión y las señales de mayor certeza. Responde en español.",
        max_tokens=1000
    )

    print("[agente_digestor] Generando decisiones finales...")
    decision = await chat(
        mensajes=[{"role": "user", "content": "Basándote en este reporte, toma decisiones de inversión:\n" + reporte["texto"]}],
        system="Eres el agente financiero principal. Toma decisiones claras de inversión. Formato: ACCION (COMPRAR/VENDER/MANTENER), SIMBOLO, RAZON (1 oración), CONFIANZA (1-10), HORIZONTE. Máximo 5 decisiones priorizadas por oportunidad. Responde en español.",
        max_tokens=600
    )

    return {
        "timestamp":          timestamp,
        "reporte_consolidado": reporte["texto"],
        "decisiones":         decision["texto"],
        "modelo":             reporte["modelo"]
    }

async def ejecutar_ciclo_completo() -> dict:
    from agente_financiero.noticias_web import obtener_noticias_mercado
    from agente_financiero.agente_sentimiento import obtener_reporte_sentimiento
    from agente_financiero.agente_macro import obtener_reporte_macro
    from agente_financiero.agente_historico import obtener_reporte_historico
    from agente_financiero.agente_fundamental import obtener_reporte_fundamental

    print("\n=== INICIANDO CICLO COMPLETO ===\n")

    noticias    = obtener_noticias_mercado()
    sentimiento = await obtener_reporte_sentimiento()
    macro       = await obtener_reporte_macro()
    historico   = await obtener_reporte_historico()
    fundamental = await obtener_reporte_fundamental()

    resultado = await consolidar_reportes(
        reporte_noticias=noticias,
        reporte_sentimiento=sentimiento,
        reporte_macro=macro,
        reporte_historico=historico,
        reporte_fundamental=fundamental,
    )

    print("\n=== REPORTE EJECUTIVO ===")
    print(resultado["reporte_consolidado"])
    print("\n=== DECISIONES ===")
    print(resultado["decisiones"])
    print(f"\nModelo usado: {resultado['modelo']}")

    return resultado