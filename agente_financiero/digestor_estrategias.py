# agente_financiero/digestor_estrategias.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from nucleo.cliente_ia import chat
from agente_financiero.agente_orb import ejecutar_analisis_orb
from agente_financiero.agente_vwap_reversion import ejecutar_vwap_reversion
from agente_financiero.agente_gap_go import ejecutar_gap_go
from agente_financiero.agente_mean_reversion import ejecutar_mean_reversion
from agente_financiero.agente_news_momentum import ejecutar_news_momentum
from agente_financiero.agente_vix_nasdaq import obtener_señal_actual as obtener_señal_vix

ACTIVOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT",
           "AAPL", "NVDA", "MSFT", "TSLA", "SPY", "QQQ"]

async def ejecutar_ciclo_estrategias() -> dict:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[digestor_estrategias] Ciclo estrategias {timestamp}")

    # Corre todas las estrategias en paralelo
    print("[1/5] ORB, VWAP, Gap, Mean, News en paralelo...")
    orb_res, vwap_res, gap_res, mean_res, news_res, vix_res = await asyncio.gather(
        asyncio.to_thread(ejecutar_analisis_orb),
        asyncio.to_thread(ejecutar_vwap_reversion),
        asyncio.to_thread(ejecutar_gap_go),
        asyncio.to_thread(ejecutar_mean_reversion),
        asyncio.to_thread(ejecutar_news_momentum),
        asyncio.to_thread(obtener_señal_vix),
    )

    # Agrega señal VIX a QQQ y SPY
    if "error" not in vix_res and vix_res.get("accion") != "ESPERAR":
        for simbolo in ["QQQ", "SPY"]:
            if simbolo in tabla:
                tabla[simbolo]["vix"] = vix_res.get("accion", "ESPERAR")
    print(f"[digestor_estrategias] VIX: {vix_res.get('señal','N/A')} | {vix_res.get('fuerza','N/A')}")

    # Consolida señales por activo
    tabla = {}
    for activo in ACTIVOS:
        tabla[activo] = {
            "simbolo": activo,
            "orb":     None,
            "vwap":    None,
            "gap":     None,
            "mean":    None,
            "news":    None,
            "vix":     None,
        }

    # Llena tabla con resultados
    for r in orb_res:
        s = r.get("simbolo", "")
        if s in tabla:
            tabla[s]["orb"] = r.get("señal", "ESPERAR")

    for r in vwap_res:
        s = r.get("simbolo", "")
        if s in tabla:
            tabla[s]["vwap"] = r.get("señal", "ESPERAR")

    for r in gap_res:
        s = r.get("simbolo", "")
        if s in tabla:
            tabla[s]["gap"] = r.get("señal", "ESPERAR")

    for r in mean_res:
        s = r.get("simbolo", "")
        if s in tabla:
            tabla[s]["mean"] = r.get("señal", "ESPERAR")

    for r in news_res:
        s = r.get("simbolo", "")
        # Mapea BTC/ETH a BTCUSDT/ETHUSDT
        if s == "BTC":
            s = "BTCUSDT"
        elif s == "ETH":
            s = "ETHUSDT"
        if s in tabla:
            tabla[s]["news"] = r.get("señal", "ESPERAR")

    # Calcula confluencia por activo
    resultados = []
    for activo, datos in tabla.items():
        señales = [v for k, v in datos.items() if k != "simbolo" and v is not None]
        votos_compra = señales.count("COMPRAR")
        votos_venta  = señales.count("VENDER")
        total_votos  = votos_compra + votos_venta

        if votos_compra >= 3:
            señal_final = "COMPRAR"
            confluencia = "MUY_ALTA"
            confianza   = min(50 + votos_compra * 10, 95)
        elif votos_compra >= 2:
            señal_final = "COMPRAR"
            confluencia = "ALTA"
            confianza   = 70
        elif votos_venta >= 3:
            señal_final = "VENDER"
            confluencia = "MUY_ALTA"
            confianza   = min(50 + votos_venta * 10, 95)
        elif votos_venta >= 2:
            señal_final = "VENDER"
            confluencia = "ALTA"
            confianza   = 70
        else:
            señal_final = "ESPERAR"
            confluencia = "BAJA"
            confianza   = 30

        resultados.append({
            "simbolo":      activo,
            "señal_final":  señal_final,
            "confluencia":  confluencia,
            "confianza":    confianza,
            "votos_compra": votos_compra,
            "votos_venta":  votos_venta,
            "orb":          datos["orb"],
            "vwap":         datos["vwap"],
            "gap":          datos["gap"],
            "mean":         datos["mean"],
            "news":         datos["news"],
        })

    señales_fuertes = [r for r in resultados if r["confluencia"] in ["ALTA", "MUY_ALTA"]]

    # Resumen para IA
    resumen = "\n".join([
        f"{r['simbolo']}: {r['señal_final']} | {r['confluencia']} | conf={r['confianza']}% | "
        f"C={r['votos_compra']} V={r['votos_venta']} | "
        f"ORB={r['orb']} VWAP={r['vwap']} GAP={r['gap']} MEAN={r['mean']} NEWS={r['news']}"
        for r in resultados
    ])

    print("[digestor_estrategias] Generando analisis con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"SEÑALES DE ESTRATEGIAS:\n{resumen}"}],
        system="""Eres el digestor de estrategias de trading. Recibes señales de 5 estrategias:
ORB (opening range breakout), VWAP Reversion, Gap & Go, Mean Reversion y News Momentum.
Entrega decisiones ejecutables SOLO para señales con confluencia ALTA o MUY_ALTA.

Formato:
ESTRATEGIA_N:
- ACCION: COMPRAR o VENDER
- SIMBOLO: nombre
- ESTRATEGIAS_CONFIRMACION: lista
- CONFIANZA: porcentaje
- RAZON: una oracion
- HORIZONTE: 5min o 15min o 1hora

Si no hay señales fuertes: SIN_SEÑALES_ESTRATEGIAS
Responde en español sin texto adicional.""",
        max_tokens=600
    )

    return {
        "timestamp":       timestamp,
        "resultados":      resultados,
        "señales_fuertes": señales_fuertes,
        "decision":        respuesta["texto"],
        "modelo":          respuesta["modelo"],
    }