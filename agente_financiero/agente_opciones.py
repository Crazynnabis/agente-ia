# agente_financiero/agente_opciones.py
import requests
import numpy as np
from datetime import datetime, timedelta

ACTIVOS_OPCIONES = {
    "BTC": "BTC",
    "ETH": "ETH",
}

def obtener_opciones_deribit(moneda: str = "BTC") -> dict:
    try:
        # Obtiene todos los instrumentos de opciones
        url = "https://www.deribit.com/api/v2/public/get_instruments"
        r   = requests.get(url, params={
            "currency": moneda,
            "kind":     "option",
        }, timeout=15)
        instrumentos = r.json().get("result", [])

        if not instrumentos:
            return {"error": "Sin instrumentos"}

        # Filtra opciones que vencen en los proximos 30 dias
        ahora    = datetime.utcnow()
        limite   = ahora + timedelta(days=30)
        limite_ts = int(limite.timestamp() * 1000)

        opciones_filtradas = [
            i for i in instrumentos
            if i.get("expiration_timestamp", 0) <= limite_ts
        ]

        if not opciones_filtradas:
            opciones_filtradas = instrumentos[:50]

        # Obtiene book de cada opcion para volumen
        calls_vol = 0
        puts_vol  = 0
        calls_oi  = 0
        puts_oi   = 0
        strikes_calls = []
        strikes_puts  = []

        for instrumento in opciones_filtradas[:30]:
            nombre = instrumento["instrument_name"]
            tipo   = instrumento.get("option_type", "")

            try:
                r2 = requests.get(
                    "https://www.deribit.com/api/v2/public/get_order_book",
                    params={"instrument_name": nombre, "depth": 1},
                    timeout=5
                )
                book = r2.json().get("result", {})
                vol  = float(book.get("stats", {}).get("volume", 0))
                oi   = float(book.get("open_interest", 0))
                strike = float(instrumento.get("strike", 0))

                if tipo == "call":
                    calls_vol     += vol
                    calls_oi      += oi
                    strikes_calls.append(strike)
                elif tipo == "put":
                    puts_vol      += vol
                    puts_oi       += oi
                    strikes_puts.append(strike)
            except:
                continue

        # Calcula Put/Call Ratio
        pcr_volumen = round(puts_vol / calls_vol, 3) if calls_vol > 0 else 1.0
        pcr_oi      = round(puts_oi  / calls_oi,  3) if calls_oi  > 0 else 1.0

        # Interpretacion
        # PCR > 1.2 = exceso de puts = mercado bajista = precio puede subir (contrarian)
        # PCR < 0.8 = exceso de calls = mercado alcista = precio puede bajar (contrarian)
        if pcr_volumen > 1.3:
            señal  = "COMPRAR"
            fuerza = "alta"
            razon  = f"PCR={pcr_volumen} — exceso de Puts, mercado demasiado bajista, rebote probable"
        elif pcr_volumen > 1.1:
            señal  = "COMPRAR"
            fuerza = "media"
            razon  = f"PCR={pcr_volumen} — sesgo bajista en opciones, posible rebote"
        elif pcr_volumen < 0.7:
            señal  = "VENDER"
            fuerza = "alta"
            razon  = f"PCR={pcr_volumen} — exceso de Calls, mercado demasiado alcista, caida probable"
        elif pcr_volumen < 0.9:
            señal  = "VENDER"
            fuerza = "media"
            razon  = f"PCR={pcr_volumen} — sesgo alcista en opciones, precaucion"
        else:
            señal  = "ESPERAR"
            fuerza = "baja"
            razon  = f"PCR={pcr_volumen} — mercado equilibrado en opciones"

        # Max Pain — precio donde mas opciones expiran sin valor
        max_pain = None
        if strikes_calls and strikes_puts:
            todos_strikes = sorted(set(strikes_calls + strikes_puts))
            max_pain      = todos_strikes[len(todos_strikes)//2] if todos_strikes else None

        return {
            "moneda":       moneda,
            "calls_vol":    round(calls_vol, 2),
            "puts_vol":     round(puts_vol, 2),
            "calls_oi":     round(calls_oi, 2),
            "puts_oi":      round(puts_oi, 2),
            "pcr_volumen":  pcr_volumen,
            "pcr_oi":       pcr_oi,
            "max_pain":     max_pain,
            "señal":        señal,
            "fuerza":       fuerza,
            "razon":        razon,
            "opciones_analizadas": len(opciones_filtradas[:30]),
            "timestamp":    datetime.now().strftime("%H:%M:%S"),
        }
    except Exception as e:
        return {"moneda": moneda, "error": str(e)}

def analizar_opciones_completo() -> list:
    resultados = []
    for nombre, moneda in ACTIVOS_OPCIONES.items():
        print(f"[agente_opciones] Analizando {nombre} options...")
        r = obtener_opciones_deribit(moneda)
        if "error" not in r:
            resultados.append(r)
    return resultados

def obtener_reporte_opciones() -> str:
    resultados = analizar_opciones_completo()
    lineas = []
    for r in resultados:
        lineas.append(
            f"{r['moneda']}: {r['señal']} ({r['fuerza']}) | "
            f"PCR={r['pcr_volumen']} | MaxPain=${r['max_pain']} | {r['razon']}"
        )
    return "\n".join(lineas) if lineas else "Sin datos de opciones"