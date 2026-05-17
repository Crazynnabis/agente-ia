# agente_financiero/digestor_riesgo.py
import asyncio
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from nucleo.cliente_ia import chat
from agente_financiero.gestion_riesgo import GestorRiesgo
from agente_financiero.filtro_tendencia import filtrar_señal_por_tendencia
from agente_financiero.horario_trading import debe_operar
from agente_financiero.logger_trading import log_señal, obtener_estadisticas_dia

# Instancia global del gestor
gestor = GestorRiesgo()

async def procesar_señal(señal: dict) -> dict:
    simbolo = señal.get("simbolo", "")
    accion  = señal.get("señal_final", "ESPERAR")
    precio  = señal.get("precio", 0)
    sl      = señal.get("stop_loss", 0)
    tp1     = señal.get("take_profit_1", 0)
    tp2     = señal.get("take_profit_2", 0)

    resultado = {
        "simbolo":          simbolo,
        "accion":           accion,
        "precio":           precio,
        "aprobada_final":   False,
        "razones_rechazo":  [],
        "warnings":         [],
        "tamaño_posicion":  {},
        "tendencia":        {},
        "horario":          {},
        "riesgo":           {},
    }

    # 1. Verificar horario
    horario = debe_operar()
    resultado["horario"] = horario
    if not horario["operar"]:
        resultado["razones_rechazo"].append(horario["razon"])

    # 2. Filtrar por tendencia mayor
    filtro = filtrar_señal_por_tendencia(señal)
    resultado["tendencia"] = filtro
    if not filtro["aprobada"]:
        resultado["razones_rechazo"].append(filtro["razon"])

    # 3. Validar riesgo y tamaño
    validacion = gestor.validar_señal(señal)
    resultado["riesgo"] = validacion
    resultado["tamaño_posicion"] = validacion.get("tamaño", {})
    if not validacion["aprobada"]:
        resultado["razones_rechazo"].extend(validacion["errores"])
    resultado["warnings"].extend(validacion.get("warnings", []))

    # Aprobacion final — todos los filtros deben pasar
    resultado["aprobada_final"] = len(resultado["razones_rechazo"]) == 0

    # Registrar en logger
    # Construye lista de fuentes que confirmaron la señal
    fuentes_confirmacion = []
    if señal.get("señal_basico")    != "ESPERAR": fuentes_confirmacion.append("tecnico")
    if señal.get("señal_avanzado")  != "ESPERAR": fuentes_confirmacion.append("avanzado")
    if señal.get("señal_estrategia")!= "ESPERAR": fuentes_confirmacion.append("estrategias")
    if señal.get("sesgo_contexto")  != "NEUTRAL":  fuentes_confirmacion.append("contexto")
    if not fuentes_confirmacion:
        fuentes_confirmacion = ["tecnico"]

    log_señal(
        simbolo=simbolo,
        accion=accion,
        precio=precio,
        sl=sl,
        tp1=tp1,
        tp2=tp2,
        confianza=señal.get("confianza_final", 0),
        fuentes=fuentes_confirmacion,
        razon=señal.get("razon", ""),
        horizonte=señal.get("horizonte", "15min"),
        aprobada_riesgo=validacion["aprobada"],
        aprobada_tendencia=filtro["aprobada"],
        tamaño_posicion=resultado["tamaño_posicion"],
    )

    return resultado

async def ejecutar_digestor_riesgo(señales: list, sesgo_contexto: str = "NEUTRAL") -> dict:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[digestor_riesgo] Procesando {len(señales)} señales...")

    # Verifica horario global
    horario = debe_operar()
    if not horario["operar"]:
        print(f"[digestor_riesgo] Fuera de horario: {horario['razon']}")
        return {
            "timestamp":         timestamp,
            "operar":            False,
            "razon":             horario["razon"],
            "señales_aprobadas": [],
            "señales_rechazadas": señales,
        }

    señales_aprobadas  = []
    señales_rechazadas = []

    for señal in señales:
        if señal.get("señal_final") == "ESPERAR":
            continue

        print(f"[digestor_riesgo] Procesando {señal.get('simbolo')}...")

        # Filtro de contexto — evita operar contra el sesgo macro
        accion = señal.get("señal_final", "ESPERAR")
        if sesgo_contexto == "BAJISTA" and accion == "COMPRAR":
            print(f"  RECHAZADA por contexto BAJISTA")
            señales_rechazadas.append({"simbolo": señal.get("simbolo"), "razones_rechazo": ["Contexto macro BAJISTA — evitar compras"]})
            continue
        elif sesgo_contexto == "ALCISTA" and accion == "VENDER":
            print(f"  RECHAZADA por contexto ALCISTA")
            señales_rechazadas.append({"simbolo": señal.get("simbolo"), "razones_rechazo": ["Contexto macro ALCISTA — evitar ventas"]})
            continue

        resultado = await procesar_señal(señal)

        if resultado["aprobada_final"]:
            señales_aprobadas.append(resultado)
            print(f"  APROBADA: {señal.get('simbolo')} {señal.get('señal_final')}")
        else:
            señales_rechazadas.append(resultado)
            print(f"  RECHAZADA: {', '.join(resultado['razones_rechazo'])}")

    # Limita a max_operaciones del horario
    max_ops = horario.get("max_operaciones", 2)
    if len(señales_aprobadas) > max_ops:
        # Prioriza por confianza
        señales_aprobadas = sorted(
            señales_aprobadas,
            key=lambda x: x.get("riesgo", {}).get("tamaño", {}).get("cantidad", 0),
            reverse=True
        )[:max_ops]
        print(f"[digestor_riesgo] Limitado a {max_ops} operaciones por horario")

    # Resumen con IA
    if señales_aprobadas:
        resumen = "\n".join([
            f"{s['simbolo']}: {s['accion']} @ {s['precio']} | "
            f"SL={s.get('riesgo',{}).get('tamaño',{}).get('distancia_sl_pct','N/A')}% | "
            f"cantidad={s.get('tamaño_posicion',{}).get('cantidad','N/A')} | "
            f"tendencia={s.get('tendencia',{}).get('tendencia',{}).get('tendencia_mayor','N/A')}"
            for s in señales_aprobadas
        ])

        respuesta = await chat(
            mensajes=[{"role": "user", "content": f"Analiza estas señales de trading que pasaron filtros de riesgo:\n{resumen}\n\nDescribe en 2 oraciones el contexto tecnico que las justifica."}],
            system="Eres un analista tecnico de mercados financieros. Describe el contexto tecnico de las señales. No menciones asesoramiento ni recomendaciones. Solo describe los indicadores. Responde en español.",
            max_tokens=300
        )
        confirmacion = respuesta["texto"]
    else:
        confirmacion = "Ninguna señal pasó todos los filtros de riesgo en este ciclo."

    stats = obtener_estadisticas_dia()

    return {
        "timestamp":          timestamp,
        "operar":             True,
        "horario":            horario,
        "señales_aprobadas":  señales_aprobadas,
        "señales_rechazadas": señales_rechazadas,
        "confirmacion_ia":    confirmacion,
        "estadisticas_dia":   stats,
    }