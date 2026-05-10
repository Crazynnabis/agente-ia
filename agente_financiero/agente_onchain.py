# agente_financiero/agente_onchain.py
import asyncio
import requests
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from nucleo.cliente_ia import chat

def obtener_datos_blockchain_btc() -> dict:
    try:
        # Datos de mempool y actividad on-chain
        r = requests.get("https://mempool.space/api/v1/fees/recommended", timeout=10)
        fees = r.json()

        # Estadisticas generales de blockchain
        r2 = requests.get("https://mempool.space/api/v1/mining/hashrate/3m", timeout=10)
        hashrate_data = r2.json()

        # Bloques recientes
        r3 = requests.get("https://mempool.space/api/blocks", timeout=10)
        bloques = r3.json()[:5]

        # Precio actual desde Binance
        r4 = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", timeout=10)
        precio = float(r4.json()["price"])

        hashrate_actual = hashrate_data.get("currentHashrate", 0) if isinstance(hashrate_data, dict) else 0

        return {
            "precio_btc":        precio,
            "fee_lento":         fees.get("hourFee", 0),
            "fee_medio":         fees.get("halfHourFee", 0),
            "fee_rapido":        fees.get("fastestFee", 0),
            "hashrate_actual":   hashrate_actual,
            "txs_en_mempool":    bloques[0].get("tx_count", 0) if bloques else 0,
            "tamaño_bloque":     bloques[0].get("size", 0) if bloques else 0,
        }
    except Exception as e:
        return {"error": f"Error BTC onchain: {e}"}

def obtener_flujo_exchanges() -> dict:
    try:
        # CryptoQuant API alternativa gratuita via Firecrawl
        # Usamos alternative.me para datos de dominancia
        r = requests.get("https://api.alternative.me/v2/ticker/1/?convert=USD", timeout=10)
        data = r.json()["data"]["1"]

        # Dominancia de BTC desde CoinGecko
        r2 = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
        global_data = r2.json().get("data", {})
        dominancia_btc = global_data.get("market_cap_percentage", {}).get("btc", 0)
        dominancia_eth = global_data.get("market_cap_percentage", {}).get("eth", 0)
        volumen_total  = global_data.get("total_volume", {}).get("usd", 0)
        market_cap     = global_data.get("total_market_cap", {}).get("usd", 0)

        # Cambio de dominancia — señal importante
        return {
            "dominancia_btc":   round(dominancia_btc, 2),
            "dominancia_eth":   round(dominancia_eth, 2),
            "volumen_24h_usd":  volumen_total,
            "market_cap_total": market_cap,
            "ratio_vol_mcap":   round((volumen_total / market_cap * 100), 2) if market_cap > 0 else 0,
        }
    except Exception as e:
        return {"error": f"Error flujo exchanges: {e}"}

def obtener_datos_eth() -> dict:
    try:
        # Gas prices de ETH
        r = requests.get("https://api.etherscan.io/api?module=gastracker&action=gasoracle&apikey=YourApiKeyToken", timeout=10)
        gas_data = r.json().get("result", {})

        # Precio ETH
        r2 = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT", timeout=10)
        precio_eth = float(r2.json()["price"])

        return {
            "precio_eth":    precio_eth,
            "gas_lento":     gas_data.get("SafeGasPrice", "N/A"),
            "gas_medio":     gas_data.get("ProposeGasPrice", "N/A"),
            "gas_rapido":    gas_data.get("FastGasPrice", "N/A"),
        }
    except Exception as e:
        return {"precio_eth": 0, "gas_lento": "N/A", "gas_medio": "N/A", "gas_rapido": "N/A"}

def interpretar_señales_onchain(btc: dict, flujo: dict, eth: dict) -> dict:
    señales = []

    # Fee de BTC — alto indica alta actividad y demanda
    fee_rapido = btc.get("fee_rapido", 0)
    if isinstance(fee_rapido, (int, float)):
        if fee_rapido > 50:
            señales.append("ALTA_ACTIVIDAD_BTC — fees elevados indican demanda fuerte")
        elif fee_rapido < 5:
            señales.append("BAJA_ACTIVIDAD_BTC — red poco congestionada, posible acumulacion silenciosa")

    # Dominancia BTC — alta indica rotacion hacia BTC (risk off crypto)
    dom_btc = flujo.get("dominancia_btc", 0)
    if dom_btc > 55:
        señales.append(f"DOMINANCIA_BTC_ALTA ({dom_btc}%) — capital fluyendo a BTC, altcoins en riesgo")
    elif dom_btc < 45:
        señales.append(f"DOMINANCIA_BTC_BAJA ({dom_btc}%) — altseason posible, ETH y SOL favorecidos")

    # Ratio volumen/market cap — alto indica actividad especulativa
    ratio = flujo.get("ratio_vol_mcap", 0)
    if ratio > 10:
        señales.append(f"VOLUMEN_ALTO ({ratio}% del mcap) — alta especulacion, volatilidad esperada")
    elif ratio < 3:
        señales.append(f"VOLUMEN_BAJO ({ratio}% del mcap) — mercado consolidando, esperar ruptura")

    return {
        "señales":      señales,
        "dominancia_btc": dom_btc,
        "fee_btc":      fee_rapido,
        "ratio_vol":    ratio,
    }

async def analizar_onchain_completo() -> dict:
    print("[agente_onchain] Obteniendo datos BTC blockchain...")
    btc = obtener_datos_blockchain_btc()

    print("[agente_onchain] Obteniendo flujo de exchanges y dominancia...")
    flujo = obtener_flujo_exchanges()

    print("[agente_onchain] Obteniendo datos ETH...")
    eth = obtener_datos_eth()

    print("[agente_onchain] Interpretando señales on-chain...")
    señales = interpretar_señales_onchain(btc, flujo, eth)

    contexto = f"""
DATOS ON-CHAIN BTC:
Precio: ${btc.get('precio_btc', 'N/A')}
Fee rápido: {btc.get('fee_rapido', 'N/A')} sat/vB
Fee medio: {btc.get('fee_medio', 'N/A')} sat/vB
Hashrate: {btc.get('hashrate_actual', 'N/A')} TH/s

DATOS ETH:
Precio: ${eth.get('precio_eth', 'N/A')}
Gas rápido: {eth.get('gas_rapido', 'N/A')} gwei

DOMINANCIA Y MERCADO GLOBAL:
Dominancia BTC: {flujo.get('dominancia_btc', 'N/A')}%
Dominancia ETH: {flujo.get('dominancia_eth', 'N/A')}%
Market Cap total: ${flujo.get('market_cap_total', 0):,.0f}
Volumen 24h: ${flujo.get('volumen_24h_usd', 0):,.0f}
Ratio Vol/MCap: {flujo.get('ratio_vol_mcap', 'N/A')}%

SEÑALES DETECTADAS:
{chr(10).join(señales.get('señales', ['Sin señales claras']))}
"""

    print("[agente_onchain] Generando analisis con IA...")
    respuesta = await chat(
        mensajes=[{"role": "user", "content": f"Analiza estos datos on-chain:\n{contexto}"}],
        system="""Eres un analista on-chain experto en Bitcoin y Ethereum.
Analiza los datos de blockchain y entrega:
1. Estado actual de la red BTC y ETH
2. Señales de acumulacion o distribucion institucional
3. Impacto de la dominancia en altcoins
4. Oportunidades detectadas basadas en datos on-chain
5. Riesgos on-chain identificados
6. Recomendacion: favorable o desfavorable para comprar crypto ahora
Responde en español, conciso y accionable.""",
        max_tokens=800
    )

    return {
        "btc":       btc,
        "eth":       eth,
        "flujo":     flujo,
        "señales":   señales,
        "analisis":  respuesta["texto"],
        "modelo":    respuesta["modelo"],
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }

async def obtener_reporte_onchain() -> str:
    resultado = await analizar_onchain_completo()
    return resultado.get("analisis", "Sin analisis on-chain")