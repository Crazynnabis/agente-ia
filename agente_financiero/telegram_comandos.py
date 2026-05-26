# agente_financiero/telegram_comandos.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import requests
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(r'C:\Users\Oscar Hernandez\.env', override=True)

TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HORA_RESUMEN_UTC     = 0
_resumen_enviado_hoy = False
ALERTA_USO_UMBRAL    = 18
_alerta_uso_enviada  = False

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
    partes = comando.strip().split()
    cmd    = partes[0].lower()

    # ── /status ──────────────────────────────────────────────
    if cmd == "/status":
        try:
            from agente_financiero.ejecutor_alpaca import obtener_portafolio, obtener_posiciones
            portafolio = obtener_portafolio()
            posiciones = obtener_posiciones()
            pnl        = portafolio.get("pnl_dia", 0)
            emoji_pnl  = "📈" if pnl >= 0 else "📉"
            return (
                f"📊 <b>Estado del sistema</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Capital: ${portafolio.get('capital_total', 0):,.2f}\n"
                f"Cash: ${portafolio.get('cash', 0):,.2f}\n"
                f"Buying power: ${portafolio.get('buying_power', 0):,.2f}\n"
                f"{emoji_pnl} P&L hoy: ${pnl:,.2f}\n"
                f"Posiciones abiertas: {len(posiciones)}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🟢 Sistema activo\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
        except Exception as e:
            return f"📊 Sistema activo — {datetime.now().strftime('%H:%M:%S')}\nError: {e}"

    # ── /rendimiento ─────────────────────────────────────────
    elif cmd == "/rendimiento":
        try:
            from agente_financiero.ejecutor_alpaca import obtener_portafolio, obtener_posiciones
            from agente_financiero.logger_trading import obtener_estadisticas_dia

            portafolio  = obtener_portafolio()
            posiciones  = obtener_posiciones()
            stats       = obtener_estadisticas_dia()
            capital     = portafolio.get("capital_total", 0)
            cash        = portafolio.get("cash", 0)
            pnl_dia     = portafolio.get("pnl_dia", 0)
            equity      = portafolio.get("equity", capital)
            pnl_abierto = sum(p["pnl_usd"] for p in posiciones)
            pnl_emoji   = "📈" if pnl_dia >= 0 else "📉"

            pos_texto = ""
            for p in posiciones:
                emoji = "🟢" if p["pnl_usd"] >= 0 else "🔴"
                pos_texto += f"{emoji} {p['simbolo']}: {p['pnl_pct']:+.2f}% (${p['pnl_usd']:+,.2f})\n"
            if not pos_texto:
                pos_texto = "Sin posiciones abiertas\n"

            return (
                f"💰 <b>Rendimiento en tiempo real</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Capital total: ${capital:,.2f}\n"
                f"Equity: ${equity:,.2f}\n"
                f"Cash disponible: ${cash:,.2f}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{pnl_emoji} <b>P&L hoy: ${pnl_dia:+,.2f}</b>\n"
                f"P&L posiciones abiertas: ${pnl_abierto:+,.2f}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"<b>Posiciones:</b>\n{pos_texto}"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Señales hoy: {stats.get('total_señales', 0)}\n"
                f"Órdenes ejecutadas: {stats.get('total_ordenes', 0)}\n"
                f"Cierres: {stats.get('total_cierres', 0)}\n"
                f"Win rate: {stats.get('win_rate', 0):.1f}%\n"
                f"P&L cerradas: ${stats.get('pnl_total_usd', 0):+,.2f}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
        except Exception as e:
            return f"Error obteniendo rendimiento: {e}"

    # ── /posiciones ──────────────────────────────────────────
    elif cmd == "/posiciones":
        try:
            from agente_financiero.ejecutor_alpaca import obtener_posiciones
            posiciones = obtener_posiciones()
            if not posiciones:
                return "📭 Sin posiciones abiertas"
            texto = "📈 <b>Posiciones abiertas:</b>\n━━━━━━━━━━━━━━━━━━\n"
            for p in posiciones:
                emoji = "🟢" if p["pnl_usd"] >= 0 else "🔴"
                texto += (
                    f"{emoji} <b>{p['simbolo']}</b>\n"
                    f"   Cantidad: {p['cantidad']}\n"
                    f"   Entrada: ${p['precio_entrada']:,.4f}\n"
                    f"   Actual: ${p['precio_actual']:,.4f}\n"
                    f"   P&L: ${p['pnl_usd']:+,.2f} ({p['pnl_pct']:+.2f}%)\n"
                )
            return texto
        except Exception as e:
            return f"Error obteniendo posiciones: {e}"

    # ── /señales ─────────────────────────────────────────────
    elif cmd in ["/señales", "/senales"]:
        try:
            from agente_financiero.logger_trading import obtener_estadisticas_dia
            stats = obtener_estadisticas_dia()
            pnl   = stats.get("pnl_total_usd", 0)
            emoji = "📈" if pnl >= 0 else "📉"
            return (
                f"📡 <b>Señales de hoy:</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Total señales: {stats.get('total_señales', 0)}\n"
                f"Órdenes ejecutadas: {stats.get('total_ordenes', 0)}\n"
                f"Cierres: {stats.get('total_cierres', 0)}\n"
                f"Ganancias: {stats.get('ganancias', 0)} | Pérdidas: {stats.get('perdidas', 0)}\n"
                f"Win rate: {stats.get('win_rate', 0):.1f}%\n"
                f"{emoji} P&L total: ${pnl:+,.2f}\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
        except Exception as e:
            return f"Error obteniendo señales: {e}"

    # ── /modo ─────────────────────────────────────────────────
    elif cmd == "/modo":
        try:
            from loop_automatico import obtener_info_modo
            info = obtener_info_modo()

            conservador = info["conservador"]
            vol_alta    = info["volatilidad_alta"]
            emoji_modo  = "🌙" if conservador else "☀️"
            modo_txt    = "CONSERVADOR" if conservador else "NORMAL"
            emoji_vol   = "🚨" if vol_alta else "✅"

            return (
                f"{emoji_modo} <b>Modo de operación actual</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Modo: <b>{modo_txt}</b>\n"
                f"Hora UTC: {info['hora_utc']:02d}:00\n"
                f"Próximo cambio: {info['siguiente_cambio']}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Confianza mínima: {info['confianza_minima']}%\n"
                f"Votos requeridos: {info['votos_minimos']}\n"
                f"Tamaño posición: {info['tamaño_posicion']}\n"
                f"ATR multiplier: {info['atr_multiplier']}x\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{emoji_vol} Volatilidad alta: {'SÍ — pausando señales <95%' if vol_alta else 'No'}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
        except Exception as e:
            return f"Error obteniendo modo: {e}"

    # ── /uso ─────────────────────────────────────────────────
    elif cmd == "/uso":
        try:
            from nucleo.cliente_ia import obtener_stats_uso, MAX_LLAMADAS_HORA
            stats       = obtener_stats_uso()
            usadas      = stats["llamadas_ultima_hora"]
            disponibles = stats["disponibles"]
            limite      = stats["limite_hora"]
            pct         = round(usadas / limite * 100) if limite > 0 else 0

            bloques_llenos = round(pct / 10)
            barra = "█" * bloques_llenos + "░" * (10 - bloques_llenos)

            if pct >= 90:   emoji_uso = "🔴"; estado_uso = "CRÍTICO"
            elif pct >= 70: emoji_uso = "🟡"; estado_uso = "ALTO"
            else:           emoji_uso = "🟢"; estado_uso = "NORMAL"

            return (
                f"🤖 <b>Uso Claude API</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{emoji_uso} Estado: {estado_uso}\n"
                f"Llamadas: {usadas}/{limite} por hora\n"
                f"Disponibles: {disponibles}\n"
                f"[{barra}] {pct}%\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Reset en: {stats.get('proximo_reset', 'N/A')}\n"
                f"Agentes prioritarios: digestor_tecnico, digestor_maestro, digestor_riesgo\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
        except Exception as e:
            return f"Error obteniendo uso Claude: {e}"

    # ── /blacklist ───────────────────────────────────────────
    elif cmd == "/blacklist":
        try:
            import time
            try:
                from loop_automatico import _estado, _lock_estado
                with _lock_estado:
                    blacklist = dict(_estado.get("blacklist", {}))
            except:
                blacklist = {}

            if not blacklist:
                return "✅ Blacklist vacía — ningún activo bloqueado"

            ahora = time.time()
            texto = "🚫 <b>Activos en blacklist:</b>\n━━━━━━━━━━━━━━━━━━\n"
            for simbolo, ts_desbloqueo in blacklist.items():
                restante = ts_desbloqueo - ahora
                if restante > 0:
                    horas   = int(restante // 3600)
                    minutos = int((restante % 3600) // 60)
                    texto  += f"🔴 {simbolo} — desbloqueado en {horas}h {minutos}m\n"
                else:
                    texto += f"🟡 {simbolo} — desbloqueando...\n"
            return texto
        except Exception as e:
            return f"Error obteniendo blacklist: {e}"

    # ── /aprendizaje ─────────────────────────────────────────
    elif cmd == "/aprendizaje":
        try:
            from agente_financiero.logger_trading import obtener_reporte_aprendizaje
            return obtener_reporte_aprendizaje()
        except Exception as e:
            return f"Error obteniendo aprendizaje: {e}"

    # ── /health ──────────────────────────────────────────────
    elif cmd == "/health":
        try:
            from agente_financiero.ejecutor_alpaca import obtener_portafolio
            from nucleo.cliente_ia import obtener_stats_uso
            errores = []
            ok      = []

            try:
                p = obtener_portafolio()
                ok.append("Alpaca API") if p else errores.append("Alpaca API")
            except:
                errores.append("Alpaca API")

            try:
                import requests as req
                r = req.get("https://api.binance.com/api/v3/ping", timeout=5)
                ok.append("Binance API") if r.status_code == 200 else errores.append("Binance API")
            except:
                errores.append("Binance API")

            try:
                from supabase import create_client
                sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
                sb.table("señales_trading").select("id").limit(1).execute()
                ok.append("Supabase")
            except:
                errores.append("Supabase")

            try:
                key   = os.getenv("ANTHROPIC_API_KEY", "")
                stats = obtener_stats_uso()
                if key and len(key) > 20:
                    ok.append(f"Claude API ✓ ({stats['llamadas_ultima_hora']}/{stats['limite_hora']}/h)")
                else:
                    errores.append("Claude API — sin créditos")
            except:
                errores.append("Claude API")

            try:
                import requests as req
                r = req.get("http://localhost:11434/api/tags", timeout=3)
                ok.append("Ollama local") if r.status_code == 200 else errores.append("Ollama local")
            except:
                errores.append("Ollama local")

            ok_txt  = "\n".join([f"✅ {x}" for x in ok])
            err_txt = "\n".join([f"❌ {x}" for x in errores])
            estado  = "🟢 SISTEMA OK" if not errores else f"🟡 {len(errores)} componente(s) con error"

            return (
                f"🔧 <b>Health Check</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{estado}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{ok_txt}\n"
                f"{err_txt if err_txt else ''}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
        except Exception as e:
            return f"Error en health check: {e}"

    # ── /cerrar ──────────────────────────────────────────────
    elif cmd == "/cerrar":
        if len(partes) < 2:
            return "❌ Uso: /cerrar SIMBOLO\nEjemplo: /cerrar BTCUSDT"
        try:
            from agente_financiero.ejecutor_alpaca import cerrar_posicion
            simbolo   = partes[1].upper()
            resultado = cerrar_posicion(simbolo, "Cierre manual via Telegram")
            if "error" in resultado:
                return f"❌ Error cerrando {simbolo}: {resultado['error']}"
            return f"✅ Posición {simbolo} cerrada manualmente"
        except Exception as e:
            return f"Error cerrando posición: {e}"

    # ── /help ────────────────────────────────────────────────
    elif cmd in ["/help", "/ayuda"]:
        return (
            "🤖 <b>Comandos disponibles:</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "/status — Estado general del sistema\n"
            "/rendimiento — P&L en tiempo real completo\n"
            "/posiciones — Posiciones abiertas con detalle\n"
            "/senales — Estadísticas de señales del día\n"
            "/modo — Modo actual y parámetros de operación\n"
            "/uso — Uso de Claude API en tiempo real\n"
            "/blacklist — Activos bloqueados y tiempo restante\n"
            "/aprendizaje — Reporte de rendimiento por activo\n"
            "/health — Estado de todos los componentes\n"
            "/cerrar SIMBOLO — Cierra posición manualmente\n"
            "/help — Esta ayuda"
        )

    else:
        return f"❓ Comando no reconocido: {cmd}\nEscribe /help para ver los comandos"

async def enviar_resumen_diario():
    try:
        from agente_financiero.ejecutor_alpaca import obtener_portafolio
        from agente_financiero.logger_trading import obtener_estadisticas_dia, obtener_reporte_aprendizaje
        from nucleo.cliente_ia import obtener_stats_uso

        portafolio = obtener_portafolio()
        stats      = obtener_estadisticas_dia()
        uso_claude = obtener_stats_uso()
        pnl_dia    = portafolio.get("pnl_dia", 0)
        pnl_emoji  = "📈" if pnl_dia >= 0 else "📉"
        win_rate   = stats.get("win_rate", 0)
        wr_emoji   = "🟢" if win_rate >= 50 else ("🟡" if win_rate >= 35 else "🔴")
        reporte    = obtener_reporte_aprendizaje()

        mensaje = (
            f"🌙 <b>Resumen diario — {datetime.now().strftime('%d/%m/%Y')}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Capital: ${portafolio.get('capital_total', 0):,.2f}\n"
            f"{pnl_emoji} P&L hoy: ${pnl_dia:+,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📡 Señales detectadas: {stats.get('total_señales', 0)}\n"
            f"⚡ Órdenes ejecutadas: {stats.get('total_ordenes', 0)}\n"
            f"🔒 Cierres: {stats.get('total_cierres', 0)}\n"
            f"✅ Ganancias: {stats.get('ganancias', 0)} | ❌ Pérdidas: {stats.get('perdidas', 0)}\n"
            f"{wr_emoji} Win rate: {win_rate:.1f}%\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🤖 Claude usado hoy: {uso_claude['llamadas_ultima_hora']} llamadas\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{reporte[:400]}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⏰ Próximo ciclo: sesión Asia 08:00 UTC"
        )
        enviar_mensaje_cmd(mensaje)
        print(f"[telegram_cmd] Resumen diario enviado")
    except Exception as e:
        print(f"[telegram_cmd] Error resumen diario: {e}")

async def verificar_alerta_uso_claude():
    global _alerta_uso_enviada
    try:
        from nucleo.cliente_ia import obtener_stats_uso, MAX_LLAMADAS_HORA
        stats  = obtener_stats_uso()
        usadas = stats["llamadas_ultima_hora"]

        if usadas >= ALERTA_USO_UMBRAL and not _alerta_uso_enviada:
            enviar_mensaje_cmd(
                f"⚠️ <b>Alerta uso Claude API</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Llamadas usadas: {usadas}/{MAX_LLAMADAS_HORA}\n"
                f"Solo quedan {MAX_LLAMADAS_HORA - usadas} llamadas disponibles\n"
                f"El sistema seguirá operando con Ollama y fallback numérico\n"
                f"Reset en: {stats.get('proximo_reset', 'N/A')}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Usa /uso para monitorear en tiempo real"
            )
            _alerta_uso_enviada = True
            print(f"[telegram_cmd] Alerta uso Claude enviada — {usadas}/{MAX_LLAMADAS_HORA}")
        elif usadas < ALERTA_USO_UMBRAL and _alerta_uso_enviada:
            _alerta_uso_enviada = False

    except Exception as e:
        print(f"[telegram_cmd] Error verificando uso Claude: {e}")

async def escuchar_comandos():
    global _resumen_enviado_hoy
    print("[telegram_cmd] Escuchando comandos...")
    offset = 0

    while True:
        try:
            hora_utc = datetime.now(timezone.utc).hour
            if hora_utc == HORA_RESUMEN_UTC and not _resumen_enviado_hoy:
                await enviar_resumen_diario()
                _resumen_enviado_hoy = True
            elif hora_utc != HORA_RESUMEN_UTC:
                _resumen_enviado_hoy = False

            await verificar_alerta_uso_claude()

            updates = obtener_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                mensaje = update.get("message", {})
                texto   = mensaje.get("text", "")

                if texto and texto.startswith("/"):
                    print(f"[telegram_cmd] Procesando comando: {texto}")
                    respuesta = await procesar_comando(texto)
                    enviar_mensaje_cmd(respuesta)

        except Exception as e:
            print(f"[telegram_cmd] Error: {e}")

        await asyncio.sleep(3)