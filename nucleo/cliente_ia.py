# nucleo/cliente_ia.py
import os
from dotenv import load_dotenv
load_dotenv(r'C:\Users\Oscar Hernandez\.env', override=True)
load_dotenv(override=False)

MODELO_CLAUDE = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
MODELO_OLLAMA = "qwen2.5-coder:7b"

def generar_decision_fallback(mensajes: list, system: str = "") -> str:
    """
    Genera decisiones de trading basadas en datos numericos
    sin necesidad de IA — parsea el contenido del mensaje.
    """
    contenido = mensajes[-1]["content"] if mensajes else ""

    # Extrae señales del texto
    lineas         = contenido.split("\n")
    decisiones     = []
    decision_num   = 1

    for linea in lineas:
        linea = linea.strip()
        if not linea:
            continue

        # Busca patrones de señales en la tabla
        partes = linea.split(":")
        if len(partes) < 2:
            continue

        simbolo = partes[0].strip()
        resto   = partes[1] if len(partes) > 1 else ""

        # Detecta señal
        if "COMPRAR" in resto and "conf=" in resto:
            try:
                conf_str  = resto.split("conf=")[1].split("%")[0].strip()
                confianza = int(conf_str)
                if confianza < 80:
                    continue

                # Extrae precio y niveles
                precio = 0
                sl     = 0
                tp1    = 0
                tp2    = 0

                if "precio=" in resto:
                    try: precio = float(resto.split("precio=")[1].split(" ")[0].strip())
                    except: pass
                if "SL=" in resto:
                    try: sl = float(resto.split("SL=")[1].split(" ")[0].strip())
                    except: pass
                if "TP1=" in resto:
                    try: tp1 = float(resto.split("TP1=")[1].split(" ")[0].strip())
                    except: pass
                if "TP2=" in resto:
                    try: tp2 = float(resto.split("TP2=")[1].split(" ")[0].strip())
                    except: pass

                if precio > 0 and sl > 0 and tp1 > 0:
                    decisiones.append(
                        f"DECISION_{decision_num}:\n"
                        f"- ACCION: COMPRAR\n"
                        f"- SIMBOLO: {simbolo}\n"
                        f"- PRECIO_ENTRADA: {precio}\n"
                        f"- STOP_LOSS: {sl}\n"
                        f"- TAKE_PROFIT_1: {tp1}\n"
                        f"- TAKE_PROFIT_2: {tp2 if tp2 > 0 else round(precio + (precio - sl) * 3, 4)}\n"
                        f"- CONFIANZA: {confianza}%\n"
                        f"- FUENTES: datos_numericos\n"
                        f"- RAZON: Confluencia numerica detectada — {confianza}% confianza\n"
                        f"- HORIZONTE: 15min"
                    )
                    decision_num += 1
            except:
                continue

        elif "VENDER" in resto and "conf=" in resto:
            try:
                conf_str  = resto.split("conf=")[1].split("%")[0].strip()
                confianza = int(conf_str)
                if confianza < 80:
                    continue

                precio = 0
                sl     = 0
                tp1    = 0
                tp2    = 0

                if "precio=" in resto:
                    try: precio = float(resto.split("precio=")[1].split(" ")[0].strip())
                    except: pass
                if "SL=" in resto:
                    try: sl = float(resto.split("SL=")[1].split(" ")[0].strip())
                    except: pass
                if "TP1=" in resto:
                    try: tp1 = float(resto.split("TP1=")[1].split(" ")[0].strip())
                    except: pass
                if "TP2=" in resto:
                    try: tp2 = float(resto.split("TP2=")[1].split(" ")[0].strip())
                    except: pass

                if precio > 0 and sl > 0 and tp1 > 0:
                    decisiones.append(
                        f"DECISION_{decision_num}:\n"
                        f"- ACCION: VENDER\n"
                        f"- SIMBOLO: {simbolo}\n"
                        f"- PRECIO_ENTRADA: {precio}\n"
                        f"- STOP_LOSS: {sl}\n"
                        f"- TAKE_PROFIT_1: {tp1}\n"
                        f"- TAKE_PROFIT_2: {tp2 if tp2 > 0 else round(precio - (sl - precio) * 3, 4)}\n"
                        f"- CONFIANZA: {confianza}%\n"
                        f"- FUENTES: datos_numericos\n"
                        f"- RAZON: Confluencia numerica detectada — {confianza}% confianza\n"
                        f"- HORIZONTE: 15min"
                    )
                    decision_num += 1
            except:
                continue

    if decisiones:
        return "\n\n".join(decisiones)
    return "SIN_SEÑALES_FUERTES"

async def chat(mensajes: list, system: str = "", max_tokens: int = 1000) -> dict:
    # Intento 1: Claude API
    try:
        import anthropic
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if api_key and len(api_key) > 20:
            cliente   = anthropic.AsyncAnthropic(api_key=api_key)
            kwargs    = {"model": MODELO_CLAUDE, "max_tokens": max_tokens, "messages": mensajes}
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
        texto     = respuesta["message"]["content"]
        # Verifica que Ollama genero una decision valida
        if any(k in texto for k in ["DECISION_", "COMPRAR", "VENDER", "SIN_SEÑALES"]):
            return {"texto": texto, "modelo": MODELO_OLLAMA, "fuente": "ollama_local"}
        else:
            print(f"[cliente_ia] Ollama no genero formato valido — usando fallback")
    except Exception as e:
        print(f"[cliente_ia] Ollama no disponible: {e}")

    # Fallback final — decision basada en datos numericos
    print(f"[cliente_ia] Usando fallback numerico")
    texto_fallback = generar_decision_fallback(mensajes, system)
    return {
        "texto":  texto_fallback,
        "modelo": "fallback_numerico",
        "fuente": "fallback"
    }