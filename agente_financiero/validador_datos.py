# agente_financiero/validador_datos.py
"""
Valida que los datos de mercado estén dentro de rangos razonables
antes de que contaminen el estado global y las decisiones de trading.
"""

import time

# ============================================================
# RANGOS VÁLIDOS POR DATO
# ============================================================
RANGOS = {
    # Put/Call Ratio BTC — rango normal 0.3 a 2.5, máximo razonable 5.0
    "pcr_btc": {
        "min": 0.1, "max": 5.0,
        "default": 1.0,
        "descripcion": "Put/Call Ratio BTC",
    },
    # WTI — rango razonable $40-$130
    "wti": {
        "min": 40.0, "max": 130.0,
        "default": 0,          # 0 = "no disponible", no contamina
        "descripcion": "Precio WTI (petróleo)",
    },
    # Fear & Greed — siempre 0-100
    "fear_greed": {
        "min": 0, "max": 100,
        "default": 50,
        "descripcion": "Fear & Greed Index",
    },
    # DXY — rango razonable 80-120
    "dxy": {
        "min": 80.0, "max": 120.0,
        "default": 0,
        "descripcion": "Índice DXY (dólar)",
    },
    # Precios BTC — rango razonable $10k-$500k
    "btc_precio": {
        "min": 10_000, "max": 500_000,
        "default": 0,
        "descripcion": "Precio BTC/USDT",
    },
    # Precios ETH — rango razonable $100-$50k
    "eth_precio": {
        "min": 100, "max": 50_000,
        "default": 0,
        "descripcion": "Precio ETH/USDT",
    },
}

# Historial de anomalías detectadas (últimas 50)
_anomalias: list = []

def validar_dato(clave: str, valor, contexto: str = "") -> tuple:
    """
    Valida un dato contra su rango esperado.
    Retorna (valor_valido, es_anomalia, mensaje)
    
    Uso:
        valor_ok, anomalia, msg = validar_dato("pcr_btc", 7.043, "loop_1h")
        if anomalia:
            print(msg)  # usar valor_ok en lugar del original
    """
    if clave not in RANGOS:
        return valor, False, ""

    rango = RANGOS[clave]

    # None o 0 para datos opcionales — no es anomalía, es "sin dato"
    if valor is None:
        return rango["default"], False, ""

    try:
        valor_float = float(valor)
    except (TypeError, ValueError):
        msg = f"[validador] {clave} no es numérico: {valor!r} — usando default {rango['default']}"
        _registrar_anomalia(clave, valor, rango["default"], msg, contexto)
        return rango["default"], True, msg

    if valor_float < rango["min"] or valor_float > rango["max"]:
        msg = (
            f"[validador] ⚠ DATO ANÓMALO — {rango['descripcion']}: "
            f"{valor_float} fuera de rango [{rango['min']}, {rango['max']}] "
            f"→ usando default {rango['default']}"
            + (f" | contexto: {contexto}" if contexto else "")
        )
        _registrar_anomalia(clave, valor_float, rango["default"], msg, contexto)
        return rango["default"], True, msg

    return valor_float, False, ""


def validar_lote(datos: dict, contexto: str = "") -> tuple:
    """
    Valida un diccionario de datos de una vez.
    Retorna (datos_limpios, lista_de_anomalias)
    
    Uso:
        datos_raw = {"pcr_btc": 7.0, "wti": 92.96, "fear_greed": 25}
        datos_ok, anomalias = validar_lote(datos_raw, "loop_1h")
    """
    datos_limpios = {}
    anomalias     = []

    for clave, valor in datos.items():
        valor_ok, es_anomalia, msg = validar_dato(clave, valor, contexto)
        datos_limpios[clave] = valor_ok
        if es_anomalia:
            anomalias.append(msg)
            print(msg)

    return datos_limpios, anomalias


def _registrar_anomalia(clave: str, valor_original, valor_default, mensaje: str, contexto: str):
    _anomalias.append({
        "ts":              time.time(),
        "clave":           clave,
        "valor_original":  valor_original,
        "valor_usado":     valor_default,
        "contexto":        contexto,
        "mensaje":         mensaje,
    })
    # Mantener solo las últimas 50
    if len(_anomalias) > 50:
        _anomalias.pop(0)


def obtener_anomalias_recientes(n: int = 10) -> list:
    """Retorna las últimas n anomalías detectadas."""
    return _anomalias[-n:]


def resumen_anomalias() -> str:
    """Texto para Telegram con anomalías de las últimas 6 horas."""
    hace_6h = time.time() - 6 * 3600
    recientes = [a for a in _anomalias if a["ts"] > hace_6h]
    if not recientes:
        return "✅ Sin anomalías en datos de mercado (últimas 6h)"
    lineas = [f"⚠ {len(recientes)} anomalías en datos (últimas 6h):"]
    for a in recientes[-5:]:
        from datetime import datetime
        hora = datetime.fromtimestamp(a["ts"]).strftime("%H:%M")
        lineas.append(f"  • {hora} {a['clave']}: {a['valor_original']} → {a['valor_usado']}")
    return "\n".join(lineas)
