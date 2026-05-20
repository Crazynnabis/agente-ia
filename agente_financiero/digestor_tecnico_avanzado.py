# agente_financiero/digestor_tecnico_avanzado.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from nucleo.cliente_ia import chat
from agente_financiero.agente_funding import analizar_funding_completo
from agente_financiero.agente_liquidaciones import analizar_liquidaciones_completo
from agente_financiero.agente_estructura import analizar_estructura_completo
from agente_financiero.agente_volume_profile import analizar_volume_profile_completo

ACTIVOS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

async def ejecutar_ciclo_avanzado() -> dict:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[digestor_avanzado] Ciclo avanzado {timestamp}")

    # Corre los 4 agentes en paralelo
    print("[1/4] Analizando funding rate y OI...")
    print("[2/4] Analizando liquidaciones y long/short...")
    print("[3/4] Analizando estructura de mercado...")
    print("[4/4] Calculando volume profile...")

    funding, liquidaciones, estructura, vp = await asyncio.gather(
        asyncio.to_thread(analizar_funding_completo),
        asyncio.to_thread(analizar_liquidaciones_completo),
        asyncio.to_thread(analizar_estructura_completo),
        asyncio.to_thread(analizar_volume_profile_completo),
    )

    tabla = []
    for simbolo in ACTIVOS:
        f = next((x for x in funding       if x.get("simbolo") == simbolo), {})
        l = next((x for x in liquidaciones if x.get("simbolo") == simbolo), {})
        e = next((x for x in estructura    if x.get("simbolo") == simbolo), {})
        v = next((x for x in vp            if x.get("simbolo") == simbolo), {})

        if not f and not l and not e and not v:
            continue

        señal_funding    = f.get("accion", "ESPERAR")
        señal_liq        = l.get("señal_final", "ESPERAR")
        señal_estructura = e.get("señal_final", "ESPERAR")
        señal_vp         = v.get("señal_final", "ESPERAR")

        votos_compra = sum([
            señal_funding    == "COMPRAR",
            señal_liq        == "COMPRAR",
            señal_estructura == "COMPRAR",
            señal_vp         == "COMPRAR",
        ])
        votos_venta = sum([
            señal_funding    == "VENDER",
            señal_liq        == "VENDER",
            señal_estructura == "VENDER",
            señal_vp         == "VENDER",
        ])

        confianza = round((max(votos_compra, votos_venta) / 4) * 100)

        if votos_compra >= 3:
            señal_final = "COMPRAR"
            confluencia = "MUY_ALTA"
            confianza   = min(confianza + 20, 99)
        elif votos_compra >= 2:
            señal_final = "COMPRAR"
            confluencia = "ALTA"
            confianza   = min(confianza + 10, 99)
        elif votos_venta >= 3:
            señal_final = "VENDER"
            confluencia = "MUY_ALTA"
            confianza   = min(confianza + 20, 99)
        elif votos_venta >= 2:
            señal_final = "VENDER"
            confluencia = "ALTA"
            confianza   = min(confianza + 10, 99)
        else:
            señal_final = "ESPERAR"
            confluencia = "BAJA"
            confianza   = max(confianza - 20, 10)

        precio         = e.get("precio", 0)
        poc            = v.get("vp_1h", {}).get("poc", 0)
        vah            = v.get("vp_1h", {}).get("vah", 0)
        val            = v.get("vp_1h", {}).get("val", 0)
        estructura_str = e.get("estructura", "N/A")
        bos            = e.get("bos", "ninguno")
        choch          = e.get("choch", "ninguno")
        funding_rate   = f.get("funding", {}).get("funding_rate", 0)
        longs_pct      = l.get("long_short", {}).get("longs_pct", 50)
        zona_liq_arr   = e.get("zona_liq_arriba", 0)
        zona_liq_ab    = e.get("zona_liq_abajo", 0)

        tabla.append({
            "simbolo":          simbolo,
            "precio":           precio,
            "señal_final":      señal_final,
            "confluencia":      confluencia,
            "confianza":        confianza,
            "votos_compra":     votos_compra,
            "votos_venta":      votos_venta,
            "señal_funding":    señal_funding,
            "señal_liq":        señal_liq,
            "señal_estructura": señal_estructura,
            "señal_vp":         señal_vp,
            "funding_rate":     funding_rate,
            "longs_pct":        longs_pct,
            "estructura":       estructura_str,
            "bos":              bos,
            "choch":            choch,
            "poc":              poc,
            "vah":              vah,
            "val":              val,
            "zona_liq_arriba":  zona_liq_arr,
            "zona_liq_abajo":   zona_liq_ab,
        })

    # Umbral 80% consistente con el resto del sistema
    señales_fuertes = [
        t for t in tabla
        if t["confluencia"] in ["ALTA", "MUY_ALTA"] and t["confianza"] >= 80
    ]

    resumen = "\n".join([
        f"{t['simbolo']}: {t['señal_final']} | {t['confluencia']} | conf={t['confianza']}% | "
        f"C={t['votos_compra']} V={t['votos_venta']} | "
        f"funding={t['funding_rate']}% | longs={t['longs_pct']}% | "
        f"estructura={t['estructura']} BOS={t['bos']} CHoCH={t['choch']} | "
        f"POC={t['poc']} VAH={t['vah']} VAL={t['val']}"
        for t in tabla
    ])

    print("[digestor_avanzado] Generando analisis con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"ANALISIS TECNICO AVANZADO:\n{resumen}"}],
        system="""Eres el digestor tecnico avanzado de un sistema de trading profesional.
Recibes datos de funding rate, liquidaciones, estructura de mercado y volume profile.
Entrega decisiones SOLO para señales con confluencia ALTA o MUY_ALTA y confianza mayor a 80%.
Formato:
DECISION_N:
- ACCION: COMPRAR o VENDER
- SIMBOLO: nombre
- PRECIO_ENTRADA: numero
- STOP_LOSS: VAL o zona liquidez abajo para compras
- TAKE_PROFIT_1: POC o VAH para compras (ratio 2:1)
- TAKE_PROFIT_2: zona liquidez arriba (ratio 3:1)
- CONFIANZA: porcentaje
- FUENTES: funding+liquidaciones+estructura+vp que confirman
- RAZON: una oracion
- HORIZONTE: 15min o 1hora o 4horas
Si no hay señales: SIN_SEÑALES_AVANZADAS
Responde en español sin texto adicional.""",
        max_tokens=600
    )

    return {
        "timestamp":       timestamp,
        "tabla":           tabla,
        "señales_fuertes": señales_fuertes,
        "decisiones":      respuesta["texto"],
        "modelo":          respuesta["modelo"],
    }