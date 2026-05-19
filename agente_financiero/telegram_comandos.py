# agente_financiero/telegram_comandos.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import requests
import asyncio
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(r'C:\Users\Oscar Hernandez\.env', override=True)

TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def enviar_mensaje_cmd(texto: str) -> bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": texto, "parse_mode": "HTML"},
            timeout=10
        )
        return r.json().get("ok", False)
    except:
        return False

def obtener_updates(offset: int = 0) -> list:
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TOKEN}/getUpdates",
            params={"offset": offset, "limit": 10, "timeout": 5},
            timeout=15
        )
        return r.json().get("result", [])
    except:
        return []

async def procesar_comando(comando: str) -> str:
    comando = comando.lower().strip().split()[0]

    if comando == "/status":
        try:
            from agente_financiero.ejecutor_alpaca import obtener_portafolio
            portafolio = obtener_portafolio()
            return (
                f"📊 <b>Estado del sistema</b>\n"
                f"Capital: ${portafolio.get('capital_total', 0):,.2f}\n"
                f"Cash: ${portafolio.get('cash', 0):,.2f}\n"
                f"P&L día: ${portafolio.get('pnl_dia', 0):,.2f}\n"
                f"Hora: {datetime.now().strftime('%H:%M:%S')}\n"
                f"Sistema: 🟢 Activo"
            )
        except Exception as e:
            return f"📊 Sistema activo — {datetime.now().strftime('%H:%M:%S')}"

    elif comando == "/posiciones":
        try:
            from agente_financiero.ejecutor_alpaca import obtener_posiciones
            posiciones = obtener_posiciones()
            if not posiciones:
                return "📭 Sin posiciones abiertas"
            texto = "📈 <b>Posiciones abiertas:</b>\n"
            for p in posiciones:
                emoji = "🟢" if p['pnl_usd'] > 0 else "🔴"
                texto += f"{emoji} {p['simbolo']}: {p['cantidad']} @ ${p['precio_entrada']:.2f}\n"
                texto += f"   P&L: ${p['pnl_usd']:,.2f} ({p['pnl_pct']:.2f}%)\n"
            return texto
        except Exception as e:
            return f"Error obteniendo posiciones: {e}"

    elif comando == "/señales" or comando == "/senales":
        try:
            from agente_financiero.logger_trading import obtener_estadisticas_dia
            stats = obtener_estadisticas_dia()
            return (
                f"📡 <b>Señales de hoy:</b>\n"
                f"Total señales: {stats.get('total_señales', 0)}\n"
                f"Órdenes ejecutadas: {stats.get('total_ordenes', 0)}\n"
                f"P&L día: ${stats.get('pnl_dia', 0):,.2f}\n"
            )
        except Exception as e:
            return f"Error obteniendo señales: {e}"

    elif comando == "/help" or comando == "/ayuda":
        return (
            "🤖 <b>Comandos disponibles:</b>\n"
            "/status — Estado del sistema\n"
            "/posiciones — Posiciones abiertas\n"
            "/senales — Señales del día\n"
            "/help — Esta ayuda"
        )

    else:
        return f"❓ Comando no reconocido: {comando}\nEscribe /help para ver los comandos"

async def escuchar_comandos():
    print("[telegram_cmd] Escuchando comandos...")
    offset = 0

    while True:
        try:
            updates = obtener_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                mensaje = update.get("message", {})
                texto   = mensaje.get("text", "")
                chat_id_msg = mensaje.get("chat", {}).get("id", 0)

                print(f"[telegram_cmd] Update recibido: chat_id={chat_id_msg} texto={texto}")

                if texto and texto.startswith("/"):
                    print(f"[telegram_cmd] Procesando comando: {texto}")
                    respuesta = await procesar_comando(texto)
                    enviar_mensaje_cmd(respuesta)

        except Exception as e:
            print(f"[telegram_cmd] Error: {e}")

        await asyncio.sleep(3)