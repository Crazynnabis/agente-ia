import os
from dotenv import load_dotenv
load_dotenv()

MODELO_CLAUDE = MODELO_CLAUDE = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
MODELO_OLLAMA = "qwen2.5-coder:7b"

async def chat(mensajes: list, system: str = "", max_tokens: int = 1000) -> dict:
    # Intento 1: Claude API
    try:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if api_key and not api_key.startswith("sk-ant-api03-REEMPLAZA"):
            cliente  = anthropic.AsyncAnthropic(api_key=api_key)
            kwargs   = {"model": MODELO_CLAUDE, "max_tokens": max_tokens, "messages": mensajes}
            if system:
                kwargs["system"] = system
            respuesta = await cliente.messages.create(**kwargs)
            return {"texto": respuesta.content[0].text, "modelo": MODELO_CLAUDE, "fuente": "claude"}
    except Exception as e:
        print(f"[cliente_ia] Claude no disponible: {e}")

    # Intento 2: Ollama local
    try:
        import ollama as ol
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(mensajes)
        respuesta = ol.chat(model=MODELO_OLLAMA, messages=msgs)
        return {"texto": respuesta["message"]["content"], "modelo": MODELO_OLLAMA, "fuente": "ollama_local"}
    except Exception as e:
        print(f"[cliente_ia] Ollama no disponible: {e}")

    # Fallback final: respuesta estructurada sin IA
    print(f"[cliente_ia] Usando respuesta por defecto sin IA")
    return {
        "texto":   "SISTEMA_EN_ESPERA — Sin IA disponible, usando datos numericos directamente",
        "modelo":  "fallback",
        "fuente":  "fallback"
    }