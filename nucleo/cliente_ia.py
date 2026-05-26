# nucleo/cliente_ia.py
import os
import time
import json
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
MAX_LLAMADAS_HORA = 20

AGENTES_PRIORITARIOS = {
    "digestor_tecnico",
    "digestor_maestro",
    "digestor_riesgo",
}

# TODOS los demás van a Ollama — lista exhaustiva
AGENTES_SECUNDARIOS = {
    "agente_sentimiento", "agente_macro", "agente_petroleo",
    "agente_historico", "agente_fundamental", "agente_onchain",
    "agente_velas", "agente_correlaciones", "agente_digestor",
    "digestor_contexto", "digestor_avanzado", "digestor_estrategias",
    "digestor_acciones", "agente_noticias_rss", "agente_youtube",
    "agente_correlacion_dxy", "agente_estacionalidad", "agente_opciones",
    "agente_calendario",
}

_cache_respuestas    = {}
_cache_respuestas_ts = {}
TTL_CACHE_RESPUESTAS = 600  # 10 minutos

_llamadas_claude = deque()

# Cooldown cuando Claude falla por créditos — no reintenta por 1 hora
_claude_sin_creditos    = False
_claude_sin_creditos_ts = 0
COOLDOWN_SIN_CREDITOS   = 3600  # 1 hora

# Archivo persistente para Railway — sobrevive reinicios
_LOG_LLAMADAS = "/tmp/claude_calls.json"

def _cargar_llamadas_persistentes():
    """Carga llamadas previas desde disco — para Railway."""
    global _llamadas_claude
    try:
        if os.path.exists(_LOG_LLAMADAS):
            with open(_LOG_LLAMADAS, "r") as f:
                data = json.load(f)
            ahora = time.time()
            # Solo carga llamadas de la última hora
            llamadas_validas = [t for t in data if ahora - t < 3600]
            _llamadas_claude = deque(llamadas_validas)
            if llamadas_validas:
                print(f"[cliente_ia] Rate limiter restaurado: {len(llamadas_validas)} llamadas previas")
    except:
        pass

def _guardar_llamadas_persistentes():
    """Guarda llamadas en disco — para Railway."""
    try:
        with open(_LOG_LLAMADAS, "w") as f:
            json.dump(list(_llamadas_claude), f)
    except:
        pass

def _limpiar_llamadas_antiguas():
    ahora = time.time()
    while _llamadas_claude and (ahora - _llamadas_claude[0]) > 3600:
        _llamadas_claude.popleft()

def _puede_usar_claude() -> bool:
    global _claude_sin_creditos, _claude_sin_creditos_ts

    # Verifica cooldown por créditos agotados
    if _claude_sin_creditos:
        if time.time() - _claude_sin_creditos_ts < COOLDOWN_SIN_CREDITOS:
            return False
        else:
            # Cooldown expiró — intenta de nuevo
            _claude_sin_creditos = False
            print("[cliente_ia] Cooldown expirado — reintentando Claude")

    _limpiar_llamadas_antiguas()
    return len(_llamadas_claude) < MAX_LLAMADAS_HORA

def _registrar_llamada_claude():
    _llamadas_claude.append(time.time())
    _guardar_llamadas_persistentes()

def _activar_cooldown_sin_creditos():
    """Activa cooldown de 1 hora cuando Claude no tiene créditos."""
    global _claude_sin_creditos, _claude_sin_creditos_ts
    _claude_sin_creditos    = True
    _claude_sin_creditos_ts = time.time()
    # Llena el deque para que el contador muestre 20/20
    ahora = time.time()
    while len(_llamadas_claude) < MAX_LLAMADAS_HORA:
        _llamadas_claude.append(ahora)
    _guardar_llamadas_persistentes()
    print("[cliente_ia] ⛔ Sin créditos Claude — cooldown 1 hora activado")

def obtener_stats_uso() -> dict:
    _limpiar_llamadas_antiguas()
    return {
        "llamadas_ultima_hora": len(_llamadas_claude),
        "limite_hora":          MAX_LLAMADAS_HORA,
        "disponibles":          MAX_LLAMADAS_HORA - len(_llamadas_claude),
        "sin_creditos":         _claude_sin_creditos,
        "proximo_reset":        f"{int((3600 - (time.time() - _llamadas_claude[0])) / 60)}min" if _llamadas_claude else "N/A",
    }

def _generar_cache_key(mensajes: list, system: str) -> str:
    contenido = system[:100] + (mensajes[-1]["content"][:200] if mensajes else "")
    return str(hash(contenido))

# Carga llamadas previas al importar
_cargar_llamadas_persistentes()

# ============================================================
# FALLBACK NUMÉRICO
# ============================================================
def generar_decision_fallback(mensajes: list, system: str = "") -> str:
    contenido    = mensajes[-1]["content"] if mensajes else ""
    lineas       = contenido.split("\n")
    decisiones   = []
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

    es_prioritario = agente in AGENTES_PRIORITARIOS
    es_secundario  = agente in AGENTES_SECUNDARIOS
    puede_claude   = _puede_usar_claude()

    # Agentes secundarios y no clasificados van directo a Ollama
    if es_secundario or (not es_prioritario and not puede_claude):
        if not es_secundario:
            print(f"[cliente_ia] Rate limit — {agente} usando Ollama")
        return await _llamar_ollama_o_fallback(mensajes, system, agente)

    # Agentes no clasificados con cupo — pueden usar Claude
    if not es_prioritario and not es_secundario:
        if not puede_claude:
            return await _llamar_ollama_o_fallback(mensajes, system, agente)

    # Sin cupo para prioritarios — Ollama temporal
    if not puede_claude:
        print(f"[cliente_ia] Rate limit CRÍTICO — {agente} usando Ollama temporalmente")
        return await _llamar_ollama_o_fallback(mensajes, system, agente)

    # Verifica cache
    cache_key = _generar_cache_key(mensajes, system)
    ahora     = time.time()
    if cache_key in _cache_respuestas:
        edad = ahora - _cache_respuestas_ts.get(cache_key, 0)
        if edad < TTL_CACHE_RESPUESTAS:
            print(f"[cliente_ia] Cache hit — {agente} ({int(edad)}s)")
            return _cache_respuestas[cache_key]

    # Llama a Claude
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

            stats     = obtener_stats_uso()
            resultado = {
                "texto":  respuesta.content[0].text,
                "modelo": MODELO_CLAUDE,
                "fuente": "claude",
            }

            _cache_respuestas[cache_key]    = resultado
            _cache_respuestas_ts[cache_key] = ahora

            print(f"[cliente_ia] Claude OK — {agente} | uso: {stats['llamadas_ultima_hora']}/{MAX_LLAMADAS_HORA}/h")
            return resultado

    except Exception as e:
        error_str = str(e)
        # Si es error de créditos — activa cooldown inmediato
        if "credit balance is too low" in error_str or "402" in error_str:
            _activar_cooldown_sin_creditos()
        else:
            print(f"[cliente_ia] Claude no disponible: {e}")

    return await _llamar_ollama_o_fallback(mensajes, system, agente)


async def _llamar_ollama_o_fallback(mensajes: list, system: str, agente: str = "") -> dict:
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