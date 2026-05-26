# nucleo/cliente_ia.py
import os
import time
import asyncio
from collections import deque
from dotenv import load_dotenv
load_dotenv(override=True)
load_dotenv(override=False)

MODELO_CLAUDE = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
MODELO_OLLAMA = "qwen2.5-coder:7b"

# ============================================================
# RATE LIMITER — protege créditos Claude
# ============================================================
# Máximo de llamadas Claude por hora
MAX_LLAMADAS_HORA = 20

# Agentes que DEBEN usar Claude — decisiones críticas
AGENTES_PRIORITARIOS = {
    "digestor_tecnico",    # decide qué operar
    "digestor_maestro",    # decisión final
    "digestor_riesgo",     # aprueba o rechaza
}

# Agentes que usan Ollama o fallback — análisis secundario
AGENTES_SECUNDARIOS = {
    "agente_sentimiento",
    "agente_macro",
    "agente_petroleo",
    "agente_historico",
    "agente_fundamental",
    "agente_onchain",
    "digestor_contexto",
    "digestor_avanzado",
    "digestor_estrategias",
    "digestor_acciones",
}

# Cache de respuestas — evita llamadas repetidas con contexto similar
_cache_respuestas = {}
_cache_respuestas_ts = {}
TTL_CACHE_RESPUESTAS = 600  # 10 minutos

# Registro de llamadas — ventana deslizante de 1 hora
_llamadas_claude = deque()
_lock_rate = asyncio.Lock()

def _limpiar_llamadas_antiguas():
    """Elimina llamadas fuera de la ventana de 1 hora."""
    ahora = time.time()
    while _llamadas_claude and (ahora - _llamadas_claude[0]) > 3600:
        _llamadas_claude.popleft()

def _puede_usar_claude() -> bool:
    """Verifica si hay cupo para una llamada Claude."""
    _limpiar_llamadas_antiguas()
    return len(_llamadas_claude) < MAX_LLAMADAS_HORA

def _registrar_llamada_claude():
    """Registra una llamada Claude."""
    _llamadas_claude.append(time.time())

def obtener_stats_uso() -> dict:
    """Retorna estadísticas de uso de Claude."""
    _limpiar_llamadas_antiguas()
    return {
        "llamadas_ultima_hora": len(_llamadas_claude),
        "limite_hora":          MAX_LLAMADAS_HORA,
        "disponibles":          MAX_LLAMADAS_HORA - len(_llamadas_claude),
        "proximo_reset":        f"{int((3600 - (time.time() - _llamadas_claude[0])) / 60)}min" if _llamadas_claude else "N/A",
    }

def _generar_cache_key(mensajes: list, system: str) -> str:
    """Genera clave de cache basada en el contenido."""
    contenido = system[:100] + (mensajes[-1]["content"][:200] if mensajes else "")
    return str(hash(contenido))

# ============================================================
# FALLBACK NUMÉRICO
# ============================================================
def generar_decision_fallback(mensajes: list, system: str = "") -> str:
    contenido  = mensajes[-1]["content"] if mensajes else ""
    lineas     = contenido.split("\n")
    decisiones = []
    decision_num = 1

    for linea in lineas:
        linea  = linea.strip()
        if not linea:
            continue
        partes = linea.split(":")
        if len(partes) < 2:
            continue

        simbolo = partes[0].strip()
        resto   = partes[1] if len(partes) > 1 else ""

        for accion in ["COMPRAR", "VENDER"]:
            if accion in resto and "conf=" in resto:
                try:
                    conf_str  = resto.split("conf=")[1].split("%")[0].strip()
                    confianza = int(conf_str)
                    if confianza < 80:
                        continue

                    precio = sl = tp1 = tp2 = 0
                    for campo, clave in [("precio", "precio="), ("sl", "SL="), ("tp1", "TP1="), ("tp2", "TP2=")]:
                        if clave in resto:
                            try:
                                val = float(resto.split(clave)[1].split(" ")[0].strip())
                                if campo == "precio": precio = val
                                elif campo == "sl":   sl     = val
                                elif campo == "tp1":  tp1    = val
                                elif campo == "tp2":  tp2    = val
                            except: pass

                    if precio > 0 and sl > 0 and tp1 > 0:
                        tp2_calc = tp2 if tp2 > 0 else (
                            round(precio + (precio - sl) * 3, 4) if accion == "COMPRAR"
                            else round(precio - (sl - precio) * 3, 4)
                        )
                        decisiones.append(
                            f"DECISION_{decision_num}:\n"
                            f"- ACCION: {accion}\n"
                            f"- SIMBOLO: {simbolo}\n"
                            f"- PRECIO_ENTRADA: {precio}\n"
                            f"- STOP_LOSS: {sl}\n"
                            f"- TAKE_PROFIT_1: {tp1}\n"
                            f"- TAKE_PROFIT_2: {tp2_calc}\n"
                            f"- CONFIANZA: {confianza}%\n"
                            f"- FUENTES: datos_numericos\n"
                            f"- RAZON: Confluencia numerica — {confianza}% confianza\n"
                            f"- HORIZONTE: 15min"
                        )
                        decision_num += 1
                except:
                    continue

    return "\n\n".join(decisiones) if decisiones else "SIN_SEÑALES_FUERTES"

# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
async def chat(mensajes: list, system: str = "",
               max_tokens: int = 1000,
               agente: str = "") -> dict:
    """
    Llama a Claude o Ollama con rate limiting inteligente.

    agente: nombre del agente que llama — determina prioridad
    """

    # ── Determina si este agente puede usar Claude ────────────
    es_prioritario   = agente in AGENTES_PRIORITARIOS
    es_secundario    = agente in AGENTES_SECUNDARIOS
    puede_claude     = _puede_usar_claude()

    # Agentes secundarios van directo a Ollama — no gastan créditos
    if es_secundario:
        return await _llamar_ollama_o_fallback(mensajes, system, agente)

    # Agentes no clasificados con cupo disponible pueden usar Claude
    if not puede_claude and not es_prioritario:
        stats = obtener_stats_uso()
        print(f"[cliente_ia] Rate limit alcanzado ({stats['llamadas_ultima_hora']}/{MAX_LLAMADAS_HORA}/h) — {agente} usando Ollama")
        return await _llamar_ollama_o_fallback(mensajes, system, agente)

    # Sin cupo ni para prioritarios — Ollama como fallback temporal
    if not puede_claude:
        stats = obtener_stats_uso()
        print(f"[cliente_ia] Rate limit CRÍTICO — {agente} prioritario usando Ollama temporalmente")
        return await _llamar_ollama_o_fallback(mensajes, system, agente)

    # ── Verifica cache ────────────────────────────────────────
    cache_key = _generar_cache_key(mensajes, system)
    ahora     = time.time()
    if cache_key in _cache_respuestas:
        edad = ahora - _cache_respuestas_ts.get(cache_key, 0)
        if edad < TTL_CACHE_RESPUESTAS:
            print(f"[cliente_ia] Cache hit — {agente} ({int(edad)}s)")
            return _cache_respuestas[cache_key]

    # ── Llama a Claude ────────────────────────────────────────
    try:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if api_key and len(api_key) > 20:
            cliente  = anthropic.AsyncAnthropic(api_key=api_key)
            kwargs   = {
                "model":      MODELO_CLAUDE,
                "max_tokens": max_tokens,
                "messages":   mensajes,
            }
            if system:
                kwargs["system"] = system

            respuesta = await cliente.messages.create(**kwargs)
            _registrar_llamada_claude()

            stats  = obtener_stats_uso()
            resultado = {
                "texto":  respuesta.content[0].text,
                "modelo": MODELO_CLAUDE,
                "fuente": "claude",
            }

            # Guarda en cache
            _cache_respuestas[cache_key]    = resultado
            _cache_respuestas_ts[cache_key] = ahora

            print(f"[cliente_ia] Claude OK — {agente} | uso: {stats['llamadas_ultima_hora']}/{MAX_LLAMADAS_HORA}/h")
            return resultado

    except Exception as e:
        print(f"[cliente_ia] Claude no disponible: {e}")

    # ── Fallback a Ollama ─────────────────────────────────────
    return await _llamar_ollama_o_fallback(mensajes, system, agente)

async def _llamar_ollama_o_fallback(mensajes: list, system: str, agente: str = "") -> dict:
    """Intenta Ollama, si falla usa fallback numérico."""
    try:
        import ollama as ol
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(mensajes)
        respuesta = ol.chat(model=MODELO_OLLAMA, messages=msgs)
        texto     = respuesta["message"]["content"]
        if any(k in texto for k in ["DECISION_", "COMPRAR", "VENDER", "SIN_SEÑALES"]):
            return {"texto": texto, "modelo": MODELO_OLLAMA, "fuente": "ollama_local"}
        print(f"[cliente_ia] Ollama formato inválido — {agente} usando fallback")
    except Exception as e:
        print(f"[cliente_ia] Ollama no disponible: {e}")

    print(f"[cliente_ia] Fallback numérico — {agente}")
    return {
        "texto":  generar_decision_fallback(mensajes, system),
        "modelo": "fallback_numerico",
        "fuente": "fallback",
    }