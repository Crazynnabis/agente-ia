# agente_financiero/telegram_comandos.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import requests
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(override=True)

TOKEN   = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HORA_RESUMEN_UTC     = 0
_resumen_enviado_hoy = False
ALERTA_USO_UMBRAL    = 8
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
            from loop_automatico import get_estado
            portafolio = obtener_portafolio()
            posiciones = obtener_posiciones()
            pnl        = portafolio.get("pnl_dia", 0)
            emoji_pnl  = "📈" if pnl >= 0 else "📉"
            pausado    = get_estado("sistema_pausado")
            emoji_sys  = "⏸ PAUSADO" if pausado else "🟢 Activo"
            return (
                f"📊 <b>Estado del sistema</b>\n"
                f"──────────────────\n"
                f"Capital: ${portafolio.get('capital_total', 0):,.2f}\n"
                f"Cash: ${portafolio.get('cash', 0):,.2f}\n"
                f"Buying power: ${portafolio.get('buying_power', 0):,.2f}\n"
                f"{emoji_pnl} P&L hoy: ${pnl:,.2f}\n"
                f"Posiciones abiertas: {len(posiciones)}\n"
                f"──────────────────\n"
                f"{emoji_sys}\n"
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
            pos_texto   = ""
            for p in posiciones:
                emoji = "🟢" if p["pnl_usd"] >= 0 else "🔴"
                pos_texto += f"{emoji} {p['simbolo']}: {p['pnl_pct']:+.2f}% (${p['pnl_usd']:+,.2f})\n"
            if not pos_texto:
                pos_texto = "Sin posiciones abiertas\n"
            return (
                f"💰 <b>Rendimiento en tiempo real</b>\n"
                f"──────────────────\n"
                f"Capital total: ${capital:,.2f}\n"
                f"Equity: ${equity:,.2f}\n"
                f"Cash disponible: ${cash:,.2f}\n"
                f"──────────────────\n"
                f"{pnl_emoji} <b>P&L hoy: ${pnl_dia:+,.2f}</b>\n"
                f"P&L posiciones abiertas: ${pnl_abierto:+,.2f}\n"
                f"──────────────────\n"
                f"<b>Posiciones:</b>\n{pos_texto}"
                f"──────────────────\n"
                f"Señales hoy: {stats.get('total_senales', 0)}\n"
                f"Órdenes ejecutadas: {stats.get('total_ordenes', 0)}\n"
                f"Win rate: {stats.get('win_rate', 0):.1f}%\n"
                f"P&L cerradas: ${stats.get('pnl_total_usd', 0):+,.2f}\n"
                f"──────────────────\n"
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
            texto = "📊 <b>Posiciones abiertas:</b>\n──────────────────\n"
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

    # ── /senales ─────────────────────────────────────────────
    elif cmd in ["/senales", "/señales"]:
        try:
            from agente_financiero.logger_trading import obtener_estadisticas_dia
            stats = obtener_estadisticas_dia()
            pnl   = stats.get("pnl_total_usd", 0)
            emoji = "📈" if pnl >= 0 else "📉"
            return (
                f"📡 <b>Señales de hoy:</b>\n"
                f"──────────────────\n"
                f"Total señales: {stats.get('total_senales', 0)}\n"
                f"Órdenes ejecutadas: {stats.get('total_ordenes', 0)}\n"
                f"Cierres: {stats.get('total_cierres', 0)}\n"
                f"Ganancias: {stats.get('ganancias', 0)} | Pérdidas: {stats.get('perdidas', 0)}\n"
                f"Win rate: {stats.get('win_rate', 0):.1f}%\n"
                f"{emoji} P&L total: ${pnl:+,.2f}\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
        except Exception as e:
            return f"Error obteniendo señales: {e}"

    # ── /pausa ───────────────────────────────────────────────
    elif cmd == "/pausa":
        try:
            from loop_automatico import set_estado, get_estado
            import time
            if get_estado("sistema_pausado"):
                return "⏸ El sistema ya está pausado\nUsa /reanudar para continuar"
            set_estado("sistema_pausado", True)
            set_estado("sistema_pausado_ts", time.time())
            return (
                f"⏸ <b>Sistema pausado</b>\n"
                f"──────────────────\n"
                f"Los loops 15m y 2m están detenidos\n"
                f"Las posiciones abiertas siguen monitoreadas\n"
                f"El cierre automático >5% sigue activo\n"
                f"──────────────────\n"
                f"Usa /reanudar para continuar\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
        except Exception as e:
            return f"Error pausando sistema: {e}"

    # ── /reanudar ────────────────────────────────────────────
    elif cmd == "/reanudar":
        try:
            from loop_automatico import set_estado, get_estado
            from nucleo.cliente_ia import resetear_cooldown_creditos
            if not get_estado("sistema_pausado"):
                # Aunque no esté pausado, resetear cooldown si viene de recarga
                resetear_cooldown_creditos()
                return (
                    f"✅ Sistema activo\n"
                    f"Cooldown Claude reseteado — listo para operar\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
            set_estado("sistema_pausado", False)
            set_estado("sistema_pausado_ts", 0)
            resetear_cooldown_creditos()
            return (
                f"✅ <b>Sistema reanudado</b>\n"
                f"──────────────────\n"
                f"Loops 15m y 2m activos\n"
                f"Cooldown Claude reseteado\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
        except Exception as e:
            return f"Error reanudando sistema: {e}"

    # ── /errores ─────────────────────────────────────────────
    elif cmd == "/errores":
        try:
            log_file = os.path.join(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs'),
                f"errores_{datetime.now().strftime('%Y%m%d')}.log"
            )
            if not os.path.exists(log_file):
                return "✅ Sin errores registrados hoy"
            with open(log_file, "r", encoding="utf-8") as f:
                lineas = f.readlines()
            if not lineas:
                return "✅ Sin errores registrados hoy"
            ultimos = lineas[-10:]
            texto = f"⚠️ <b>Últimos errores ({len(lineas)} total hoy)</b>\n──────────────────\n"
            for linea in ultimos:
                partes = linea.strip().split(" | ")
                if len(partes) >= 3:
                    hora   = partes[0].split("T")[1][:8] if "T" in partes[0] else partes[0][:8]
                    agente = partes[1][:20]
                    error  = partes[2][:60]
                    texto += f"⏰ {hora} | {agente}\n{error}\n\n"
            return texto[:4000]
        except Exception as e:
            return f"Error leyendo log: {e}"

    # ── /modo ────────────────────────────────────────────────
    elif cmd == "/modo":
        try:
            from loop_automatico import obtener_info_modo
            info        = obtener_info_modo()
            conservador = info["conservador"]
            vol_alta    = info["volatilidad_alta"]
            pausado     = info.get("pausado", False)
            emoji_modo  = "🌙" if conservador else "☀️"
            modo_txt    = "CONSERVADOR" if conservador else "NORMAL"
            emoji_vol   = "🚨" if vol_alta else "✅"
            emoji_sys   = "⏸ PAUSADO" if pausado else "✅ Activo"
            return (
                f"{emoji_modo} <b>Modo de operación actual</b>\n"
                f"──────────────────\n"
                f"Sistema: {emoji_sys}\n"
                f"Modo: <b>{modo_txt}</b>\n"
                f"Hora UTC: {info['hora_utc']:02d}:00\n"
                f"Próximo cambio: {info['siguiente_cambio']}\n"
                f"──────────────────\n"
                f"Confianza mínima: {info['confianza_minima']}%\n"
                f"Votos requeridos: {info['votos_minimos']}\n"
                f"Tamaño posición: {info['tamano_posicion']}\n"
                f"ATR multiplier: {info['atr_multiplier']}x\n"
                f"──────────────────\n"
                f"{emoji_vol} Volatilidad alta: {'SÍ — pausando señales <95%' if vol_alta else 'No'}\n"
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
            bloques     = round(pct / 10)
            barra       = "█" * bloques + "░" * (10 - bloques)
            sin_creditos = stats.get("sin_creditos", False)
            cooldown_min = stats.get("cooldown_restante_min", 0)

            if sin_creditos:
                estado_uso = f"🔴 SIN CRÉDITOS — cooldown {cooldown_min}min"
            elif pct >= 90:
                estado_uso = "🔴 CRÍTICO"
            elif pct >= 70:
                estado_uso = "🟡 ALTO"
            else:
                estado_uso = "🟢 NORMAL"

            return (
                f"🤖 <b>Uso Claude API</b>\n"
                f"──────────────────\n"
                f"{estado_uso}\n"
                f"Llamadas: {usadas}/{limite} por hora\n"
                f"Disponibles: {disponibles}\n"
                f"[{barra}] {pct}%\n"
                f"──────────────────\n"
                f"Reset en: {stats.get('proximo_reset', 'N/A')}\n"
                f"Agentes con Claude: digestor_maestro, digestor_riesgo\n"
                f"──────────────────\n"
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
            texto = "🚫 <b>Activos en blacklist:</b>\n──────────────────\n"
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
            from loop_automatico import get_estado
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
                sb.table("senales_trading").select("id").limit(1).execute()
                ok.append("Supabase")
            except:
                errores.append("Supabase")

            try:
                stats = obtener_stats_uso()
                sin_creditos = stats.get("sin_creditos", False)
                if sin_creditos:
                    errores.append(f"Claude API — sin créditos ({stats['cooldown_restante_min']}min cooldown)")
                else:
                    ok.append(f"Claude API ({stats['llamadas_ultima_hora']}/{stats['limite_hora']}/h)")
            except:
                errores.append("Claude API")

            pausado = get_estado("sistema_pausado")
            if pausado:
                errores.append("Sistema pausado manualmente")

            ok_txt  = "\n".join([f"✅ {x}" for x in ok])
            err_txt = "\n".join([f"❌ {x}" for x in errores])
            estado  = "🟢 SISTEMA OK" if not errores else f"🟡 {len(errores)} componente(s) con error"

            return (
                f"🔧 <b>Health Check</b>\n"
                f"──────────────────\n"
                f"{estado}\n"
                f"──────────────────\n"
                f"{ok_txt}\n"
                f"{err_txt if err_txt else ''}\n"
                f"──────────────────\n"
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

    # ── /anomalias ───────────────────────────────────────────
    elif cmd == "/anomalias":
        try:
            from agente_financiero.validador_datos import resumen_anomalias
            return f"🔍 <b>Anomalías en datos de mercado</b>\n──────────────────\n{resumen_anomalias()}\n⏰ {datetime.now().strftime('%H:%M:%S')}"
        except Exception as e:
            return f"Error obteniendo anomalías: {e}"

    # ── /trailing ────────────────────────────────────────────
    elif cmd == "/trailing":
        try:
            from agente_financiero.trailing_stop import gestor_trailing
            posiciones = gestor_trailing.resumen_posiciones()
            if not posiciones:
                return "📭 Sin posiciones en trailing stop"
            texto = "📈 <b>Trailing Stop activo:</b>\n──────────────────\n"
            for p in posiciones:
                emoji = "🟢" if p["pnl_pct"] >= 0 else "🔴"
                tp1   = "✅" if p["tp1_alcanzado"] else "⏳"
                texto += (
                    f"{emoji} <b>{p['simbolo']}</b> {p['accion']}\n"
                    f"   Entrada: ${p['precio_entrada']:,.4f}\n"
                    f"   Actual: ${p['precio_actual']:,.4f}\n"
                    f"   Stop: ${p['stop_loss']:,.4f}\n"
                    f"   P&L: {p['pnl_pct']:+.2f}%\n"
                    f"   TP1: {tp1}\n\n"
                )
            return texto
        except Exception as e:
            return f"Error obteniendo trailing: {e}"

    # ── /help ────────────────────────────────────────────────
    elif cmd in ["/help", "/ayuda"]:
        return (
            "🤖 <b>Comandos disponibles:</b>\n"
            "──────────────────\n"
            "/status — Estado general del sistema\n"
            "/rendimiento — P&L en tiempo real completo\n"
            "/posiciones — Posiciones abiertas con detalle\n"
            "/senales — Estadísticas de señales del día\n"
            "/modo — Modo actual y parámetros de operación\n"
            "/uso — Uso de Claude API en tiempo real\n"
            "/blacklist — Activos bloqueados y tiempo restante\n"
            "/aprendizaje — Reporte de rendimiento por activo\n"
            "/health — Estado de todos los componentes\n"
            "/trailing — Estado del trailing stop por posición\n"
            "/anomalias — Datos de mercado anómalos detectados\n"
            "/cerrar SIMBOLO — Cierra posición manualmente\n"
            "/pausa — Pausar sistema manualmente\n"
            "/reanudar — Reanudar sistema + resetear cooldown Claude\n"
            "/errores — Ver últimos errores del día\n"
            "/help — Esta ayuda"
        )

    else:
        return f"❓ Comando no reconocido: {cmd}\nEscribe /help para ver los comandos"


async def enviar_resumen_diario():
    try:
        from agente_financiero.ejecutor_alpaca import obtener_portafolio
        from agente_financiero.logger_trading import obtener_estadisticas_dia, obtener_reporte_aprendizaje
        from nucleo.cliente_ia import obtener_stats_uso
        from agente_financiero.validador_datos import resumen_anomalias

        portafolio = obtener_portafolio()
        stats      = obtener_estadisticas_dia()
        uso_claude = obtener_stats_uso()
        pnl_dia    = portafolio.get("pnl_dia", 0)
        pnl_emoji  = "📈" if pnl_dia >= 0 else "📉"
        win_rate   = stats.get("win_rate", 0)
        wr_emoji   = "🟢" if win_rate >= 50 else ("🟡" if win_rate >= 35 else "🔴")
        reporte    = obtener_reporte_aprendizaje()
        anomalias  = resumen_anomalias()

        mensaje = (
            f"🌙 <b>Resumen diario — {datetime.now().strftime('%d/%m/%Y')}</b>\n"
            f"──────────────────\n"
            f"💰 Capital: ${portafolio.get('capital_total', 0):,.2f}\n"
            f"{pnl_emoji} P&L hoy: ${pnl_dia:+,.2f}\n"
            f"──────────────────\n"
            f"📡 Señales detectadas: {stats.get('total_senales', 0)}\n"
            f"⚡ Órdenes ejecutadas: {stats.get('total_ordenes', 0)}\n"
            f"🔒 Cierres: {stats.get('total_cierres', 0)}\n"
            f"✅ Ganancias: {stats.get('ganancias', 0)} | ❌ Pérdidas: {stats.get('perdidas', 0)}\n"
            f"{wr_emoji} Win rate: {win_rate:.1f}%\n"
            f"──────────────────\n"
            f"🤖 Claude usado hoy: {uso_claude['llamadas_ultima_hora']} llamadas\n"
            f"──────────────────\n"
            f"{reporte[:300]}\n"
            f"──────────────────\n"
            f"{anomalias}\n"
            f"──────────────────\n"
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
                f"──────────────────\n"
                f"Llamadas usadas: {usadas}/{MAX_LLAMADAS_HORA}\n"
                f"Solo quedan {MAX_LLAMADAS_HORA - usadas} llamadas disponibles\n"
                f"Reset en: {stats.get('proximo_reset', 'N/A')}\n"
                f"Usa /uso para monitorear"
            )
            _alerta_uso_enviada = True
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
                offset  = update["update_id"] + 1
                mensaje = update.get("message", {})
                texto   = mensaje.get("text", "")
                if texto and texto.startswith("/"):
                    print(f"[telegram_cmd] Procesando comando: {texto}")
                    respuesta = await procesar_comando(texto)
                    enviar_mensaje_cmd(respuesta)

        except Exception as e:
            print(f"[telegram_cmd] Error: {e}")

        await asyncio.sleep(3)
