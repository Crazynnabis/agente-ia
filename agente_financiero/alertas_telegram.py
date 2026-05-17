# agente_financiero/alertas_telegram.py
import requests
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

def enviar_mensaje(texto: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[telegram] Sin credenciales — mensaje no enviado: {texto[:50]}")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        r = requests.post(url, json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       texto,
            "parse_mode": "HTML",
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[telegram] Error: {e}")
        return False

def alerta_señal(simbolo: str, accion: str, precio: float,
                 sl: float, tp1: float, confianza: float,
                 razon: str, horizonte: str) -> bool:
    emoji = "🟢" if accion == "COMPRAR" else "🔴"
    dist_sl  = round(abs(precio - sl) / precio * 100, 2)
    dist_tp1 = round(abs(tp1 - precio) / precio * 100, 2)
    ratio    = round(dist_tp1 / dist_sl, 1) if dist_sl > 0 else 0

    texto = f"""{emoji} <b>SEÑAL DE TRADING</b>
━━━━━━━━━━━━━━━━━━
<b>Accion:</b> {accion} {simbolo}
<b>Precio entrada:</b> ${precio:,.4f}
<b>Stop Loss:</b> ${sl:,.4f} (-{dist_sl}%)
<b>Take Profit 1:</b> ${tp1:,.4f} (+{dist_tp1}%)
<b>Ratio R/B:</b> 1:{ratio}
<b>Confianza:</b> {confianza}%
<b>Horizonte:</b> {horizonte}
<b>Razon:</b> {razon}
<i>{datetime.now().strftime('%H:%M:%S UTC')}</i>"""
    return enviar_mensaje(texto)

def alerta_orden_ejecutada(simbolo: str, accion: str, precio: float,
                           cantidad: float, valor_usd: float, orden_id: str) -> bool:
    emoji = "✅" if accion == "COMPRAR" else "🔻"
    texto = f"""{emoji} <b>ORDEN EJECUTADA</b>
━━━━━━━━━━━━━━━━━━
<b>Simbolo:</b> {simbolo}
<b>Accion:</b> {accion}
<b>Precio:</b> ${precio:,.4f}
<b>Cantidad:</b> {cantidad}
<b>Valor:</b> ${valor_usd:,.2f}
<b>ID:</b> {orden_id}
<i>{datetime.now().strftime('%H:%M:%S UTC')}</i>"""
    return enviar_mensaje(texto)

def alerta_cierre(simbolo: str, precio_entrada: float,
                  precio_cierre: float, pnl_usd: float,
                  pnl_pct: float, razon: str) -> bool:
    emoji = "💰" if pnl_usd > 0 else "💸"
    signo = "+" if pnl_usd > 0 else ""
    texto = f"""{emoji} <b>POSICION CERRADA</b>
━━━━━━━━━━━━━━━━━━
<b>Simbolo:</b> {simbolo}
<b>Entrada:</b> ${precio_entrada:,.4f}
<b>Cierre:</b> ${precio_cierre:,.4f}
<b>PnL:</b> {signo}${pnl_usd:,.2f} ({signo}{pnl_pct}%)
<b>Razon:</b> {razon}
<i>{datetime.now().strftime('%H:%M:%S UTC')}</i>"""
    return enviar_mensaje(texto)

def alerta_resumen_dia(stats: dict) -> bool:
    pnl = stats.get("pnl_total_usd", 0)
    emoji = "📈" if pnl >= 0 else "📉"
    texto = f"""{emoji} <b>RESUMEN DEL DIA</b>
━━━━━━━━━━━━━━━━━━
<b>Señales detectadas:</b> {stats.get('total_señales', 0)}
<b>Ordenes ejecutadas:</b> {stats.get('total_ordenes', 0)}
<b>Operaciones cerradas:</b> {stats.get('total_cierres', 0)}
<b>Win rate:</b> {stats.get('win_rate', 0)}%
<b>PnL total:</b> ${pnl:,.2f}
<b>Ganancia promedio:</b> ${stats.get('ganancia_promedio', 0):,.2f}
<b>Perdida promedio:</b> ${stats.get('perdida_promedio', 0):,.2f}
<i>{datetime.now().strftime('%Y-%m-%d')}</i>"""
    return enviar_mensaje(texto)

def alerta_error_sistema(modulo: str, error: str) -> bool:
    texto = f"""⚠️ <b>ERROR DEL SISTEMA</b>
━━━━━━━━━━━━━━━━━━
<b>Modulo:</b> {modulo}
<b>Error:</b> {error[:200]}
<i>{datetime.now().strftime('%H:%M:%S UTC')}</i>"""
    return enviar_mensaje(texto)

def alerta_trailing_update(simbolo: str, nuevo_stop: float,
                           precio_actual: float, pnl_pct: float) -> bool:
    texto = f"""🔄 <b>TRAILING STOP ACTUALIZADO</b>
<b>Simbolo:</b> {simbolo}
<b>Precio actual:</b> ${precio_actual:,.4f}
<b>Nuevo stop:</b> ${nuevo_stop:,.4f}
<b>PnL flotante:</b> +{pnl_pct}%
<i>{datetime.now().strftime('%H:%M:%S UTC')}</i>"""
    return enviar_mensaje(texto)