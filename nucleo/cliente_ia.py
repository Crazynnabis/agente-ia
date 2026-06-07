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

MAX_LLAMADAS_HORA = 20

AGENTES_PRIORITARIOS = {
    "digestor_tecnico",
    "digestor_maestro",
    "digestor_riesgo",
}

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
TTL_CACHE_RESPUESTAS = 600

_llamadas_claude     = deque()
_claude_sin_creditos    = False
_claude_sin_creditos_ts = 0
COOLDOWN_SIN_CREDITOS   = 3600

# ============================================================
# SUPABASE — contador persistente que sobrevive reinicios
# ============================================================
def _get_supabase():
    try:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if url and key:
            return create_client(url, key)
    except:
        pass
    return None

def _cargar_estado_supabase():
    """Carga el estado de Claude desde Supabase — sobrevive reinicios de Railway."""
    global _llamadas_claude, _claude_sin_creditos, _claude_sin_creditos_ts
    try:
        sb = _get_supabase()
        if not sb:
            return
        res = sb.table("portafolio").select(
            "claude_llamadas_hora, claude_llamadas_ts, claude_cooldown, claude_cooldown_ts"
        ).eq("id", 1).execute()

        if not res.data:
            return

        data  = res.data[0]
        ahora = time.time()

        # Restaurar cooldown si sigue vigente
        cooldown_activo = data.get("claude_cooldown", False)
        cooldown_ts     = data.get("claude_cooldown_ts", 0) or 0

        if cooldown_activo and (ahora - cooldown_ts) < COOLDOWN_SIN_CREDITOS:
            _claude_sin_creditos    = True
            _claude_sin_creditos_ts = cooldown_ts
            restante = int((COOLDOWN_SIN_CREDITOS - (ahora - cooldown_ts)) / 60)
            print(f"[cliente_ia] ⚠ Cooldown restaurado desde Supabase — {restante}min restantes")
        else:
            _claude_sin_creditos    = False
            _claude_sin_creditos_ts = 0

        # Restaurar llamadas de la última hora
        llamadas     = data.get("claude_llamadas_hora", 0) or 0
        llamadas_ts  = data.get("claude_llamadas_ts", 0) or 0

        # Solo restaurar si el timestamp es de hace menos de 1 hora
        if llamadas > 0 and llamadas_ts > 0 and (ahora - llamadas_ts) < 3600:
            # Reconstruir deque con timestamps aproximados
            for i in range(llamadas):
                _llamadas_claude.append(llamadas_ts + i)
            print(f"[cliente_ia] Rate limiter restaurado desde Supabase: {llamadas} llamadas previas")
        else:
            _llamadas_claude = deque()
            print(f"[cliente_ia] Contador limpio — Claude disponible")

    except Exception as e:
        print(f"[cliente_ia] Error cargando estado Supabase: {e}")

def _guardar_estado_supabase():
    """Guarda el estado de Claude en Supabase."""
    try:
        sb = _get_supabase()
        if not sb:
            return
        _limpiar_llamadas_antiguas()
        sb.table("portafolio").update({
            "claude_llamadas_hora": len(_llamadas_claude),
            "claude_llamadas_ts":   int(time.time()),
            "claude_cooldown":      _claude_sin_creditos,
            "claude_cooldown_ts":   int(_claude_sin_creditos_ts),
        }).eq("id", 1).execute()
    except Exception as e:
        print(f"[cliente_ia] Error guardando estado Supabase: {e}")

def _limpiar_llamadas_antiguas():
    ahora = time.time()
    while _llamadas_claude and (ahora - _llamadas_claude[0]) > 3600:
        _llamadas_claude.popleft()

def _puede_usar_claude() -> bool:
    global _claude_sin_creditos, _claude_sin_creditos_ts

    if _claude_sin_creditos:
        if time.time() - _claude_sin_creditos_ts < COOLDOWN_SIN_CREDITOS:
            return False
        else:
            _claude_sin_creditos    = False
            _claude_sin_creditos_ts = 0
            _guardar_estado_supabase()
            print("[cliente_ia] Cooldown expirado — reintentando Claude")

    _limpiar_llamadas_antiguas()
    return len(_llamadas_claude) < MAX_LLAMADAS_HORA

def _registrar_llamada_claude():
    _llamadas_claude.append(time.time())
    _guardar_estado_supabase()

def _activar_cooldown_sin_creditos():
    global _claude_sin_creditos, _claude_sin_creditos_ts
    _claude_sin_creditos    = True
    _claude_sin_creditos_ts = time.time()
    ahora = time.time()
    while len(_llamadas_claude) < MAX_LLAMADAS_HORA:
        _llamadas_claude.append(ahora)
    _guardar_estado_supabase()
    print("[cliente_ia] ⚠ Sin créditos Claude — cooldown 1 hora activado en Supabase")

def resetear_cooldown_creditos():
    """
    Fuerza reset del cooldown. Llamar después de recargar créditos.
    """
    global _claude_sin_creditos, _claude_sin_creditos_ts
    _claude_sin_creditos    = False
    _claude_sin_creditos_ts = 0
    _llamadas_claude.clear()
    _guardar_estado_supabase()
    print("[cliente_ia] ✅ Cooldown reseteado — Claude disponible")

def obtener_stats_uso() -> dict:
    _limpiar_llamadas_antiguas()
    restante_cooldown = 0
    if _claude_sin_creditos:
        restante_cooldown = max(0, int((COOLDOWN_SIN_CREDITOS - (time.time() - _claude_sin_creditos_ts)) / 60))
    return {
        "llamadas_ultima_hora":  len(_llamadas_claude),
        "limite_hora":           MAX_LLAMADAS_HORA,
        "disponibles":           MAX_LLAMADAS_HORA - len(_llamadas_claude),
        "sin_creditos":          _claude_sin_creditos,
        "cooldown_restante_min": restante_cooldown,
        "proximo_reset":         f"{int((3600 - (time.time() - _llamadas_claude[0])) / 60)}min" if _llamadas_claude else "N/A",
    }

def _generar_cache_key(mensajes: list, system: str) -> str:
    contenido = system[:100] + (mensajes[-1]["content"][:200] if mensajes else "")
    return str(hash(contenido))

# Carga estado al importar
_cargar_estado_supabase()

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

    return "\n\n".join(decisiones) if decisiones else "SIN_SENALES_FUERTES"

# ============================================================
# FUNCIÓN PRINCIPAL
# ============================================================
async def chat(mensajes: list, system: str = "",
               max_tokens: int = 1000,
               agente: str = "") -> dict:

    es_prioritario = agente in AGENTES_PRIORITARIOS
    es_secundario  = agente in AGENTES_SECUNDARIOS
    puede_claude   = _puede_usar_claude()

    if es_secundario:
        return await _llamar_ollama_o_fallback(mensajes, system, agente)

    if not es_prioritario:
        print(f"[cliente_ia] Agente no clasificado — {agente} usando Ollama")
        return await _llamar_ollama_o_fallback(mensajes, system, agente)

    if not puede_claude:
        stats = obtener_stats_uso()
        if _claude_sin_creditos:
            print(f"[cliente_ia] Sin créditos — {agente} usando Ollama | cooldown {stats['cooldown_restante_min']}min")
        else:
            print(f"[cliente_ia] Rate limit {stats['llamadas_ultima_hora']}/{MAX_LLAMADAS_HORA} — {agente} usando Ollama")
        return await _llamar_ollama_o_fallback(mensajes, system, agente)

    cache_key = _generar_cache_key(mensajes, system)
    ahora     = time.time()
    if cache_key in _cache_respuestas:
        edad = ahora - _cache_respuestas_ts.get(cache_key, 0)
        if edad < TTL_CACHE_RESPUESTAS:
            print(f"[cliente_ia] Cache hit — {agente} ({int(edad)}s)")
            return _cache_respuestas[cache_key]

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
        if any(k in texto for k in ["DECISION_", "COMPRAR", "VENDER", "SIN_SENALES"]):
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
