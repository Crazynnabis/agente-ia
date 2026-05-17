import os
from dotenv import load_dotenv

load_dotenv()

MODELO_CLAUDE = "claude-opus-4-5"
MODELO_OLLAMA = "qwen2.5-coder:7b"

async def chat(mensajes: list, system: str = "", max_tokens: int = 1000) -> dict:
    try:
        import anthropic
        cliente = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        kwargs = {"model": MODELO_CLAUDE, "max_tokens": max_tokens, "messages": mensajes}
        if system:
            kwargs["system"] = system
        respuesta = await cliente.messages.create(**kwargs)
        return {"texto": respuesta.content[0].text, "modelo": MODELO_CLAUDE, "fuente": "claude"}
    except Exception as e:
        print(f"[cliente_ia] Claude no disponible, usando Ollama...")

    import ollama as ol
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(mensajes)
    respuesta = ol.chat(model=MODELO_OLLAMA, messages=msgs)
    return {"texto": respuesta["message"]["content"], "modelo": MODELO_OLLAMA, "fuente": "ollama_local"}