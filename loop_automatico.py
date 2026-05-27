# loop_automatico.py — Arquitectura de loops anidados por frecuencia
import os
import sys
import asyncio
import time
from threading import Lock

from dotenv import load_dotenv
load_dotenv(override=True)

from datetime import datetime, timezone
from supabase import create_client
from agente_financiero.digestor_maestro import ejecutar_ciclo_maestro
from agente_financiero.digestor_acciones import ejecutar_ciclo_acciones, es_horario_mercado
from agente_financiero.alertas_telegram import enviar_mensaje, alerta_resumen_dia, alerta_señal
from agente_financiero.logger_trading import obtener_estadisticas_dia
from agente_financiero.horario_trading import debe_operar, obtener_sesion_actual
from agente_financiero.agente_velas import analizar_oportunidades
from agente_financiero.agente_indicadores import analizar_indicadores_completo
from agente_financiero.agente_orderflow import analizar_todos_activos
from agente_financiero.agente_funding import analizar_funding_completo
from agente_financiero.gestion_riesgo import GestorRiesgo
from agente_financiero.ejecutor_alpaca import (
    ejecutar_orden, obtener_posiciones, obtener_portafolio,
    monitorear_perdidas_excesivas, monitorear_y_ejecutar_trailing
)
from agente_financiero.telegram_comandos import escuchar_comandos

ACTIVOS_CRYPTO       = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
UMBRAL_VOLATILIDAD   = 3.0
TTL_VOLATILIDAD_ALTA = 1800

LOG_ERRORES = os.path.join(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs'),
    f"errores_{datetime.now().strftime('%Y%m%d')}.log"
)

# ============================================================
# ESTADO GLOBAL
# ============================================================
_lock_estado = Lock()
_estado = {
    "contexto_macro":          {},
    "contexto_ts":             0,
    "sesgo_contexto":          "NEUTRAL",
    "confianza_contexto":      50,
    "fear_greed":              50,
    "wti_precio":              0,
    "estac_señal":             "NEUTRAL",
    "pcr_btc":                 1.0,
    "tabla_maestra":           [],
    "señales_fuertes":         [],
    "tabla_ts":                0,
    "blacklist":               {},
    "perdidas_consecutivas":   {},
    "volatilidad_alta":        False,
    "volatilidad_alta_ts":     0,
    "volatilidad_alta_origen": "",
    "ciclo_4h":                0,
    "ciclo_1h":                0,
    "ciclo_15m":               0,
    "ciclo_2m":                0,
    "noticias_alertas":        [],
    "dxy_señal":               "ESPERAR",
    "dxy_datos":               {},
    "modo_conservador":        False,
    "precios_anteriores":      {},
    "ballenas_señal":          "ESPERAR",
    "ballenas_ts":             0,
    "sistema_pausado":         False,
    "sistema_pausado_ts":      0,
}

gestor = GestorRiesgo()

# ============================================================
# LOG DE ERRORES
# ============================================================
def log_error(agente: str, error: str):
    try:
        os.makedirs(os.path.dirname(LOG_ERRORES), exist_ok=True)
        with open(LOG_ERRORES, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} | {agente} | {error}\n")
    except:
        pass

# ============================================================
# SUPABASE — Guarda portafolio y posiciones
# ============================================================
async def guardar_estado_supabase():
    """Guarda portafolio y posiciones en Supabase para el dashboard."""
    try:
        sb         = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
        portafolio = await asyncio.to_thread(obtener_portafolio)
        posiciones = await asyncio.to_thread(obtener_posiciones)

        sb.table("portafolio").upsert({
            "id":           1,
            "timestamp":    datetime.now().isoformat(),
            "capital_total":portafolio.get("capital_total", 0),
            "equity":       portafolio.get("equity", 0),
            "cash":         portafolio.get("cash", 0),
            "pnl_dia":      portafolio.get("pnl_dia", 0),
            "buying_power": portafolio.get("buying_power", 0),
            "sesgo":        get_estado("sesgo_contexto") or "NEUTRAL",
            "fear_greed":   get_estado("fear_greed") or 50,
            "dxy_señal":    get_estado("dxy_señal") or "ESPERAR",
            "ballenas":     get_estado("ballenas_señal") or "ESPERAR",
            "modo":         "conservador" if get_estado("modo_conservador") else "normal",
            "vol_alta":     get_estado("volatilidad_alta") or False,
            "pcr_btc":      get_estado("pcr_btc") or 1.0,
            "wti":          get_estado("wti_precio") or 0,
        }).execute()

        sb.table("posiciones").delete().neq("id", 0).execute()
        for p in posiciones:
            sb.table("posiciones").insert({
                "timestamp":      datetime.now().isoformat(),
                "simbolo":        p.get("simbolo", ""),
                "cantidad":       p.get("cantidad", 0),
                "precio_entrada": p.get("precio_entrada", 0),
                "precio_actual":  p.get("precio_actual", 0),
                "pnl_usd":        p.get("pnl_usd", 0),
                "pnl_pct":        p.get("pnl_pct", 0),
            }).execute()

        print(f"[supabase] Portafolio guardado | capital=${portafolio.get('capital_total',0):,.2f} | posiciones={len(posiciones)}")

    except Exception as e:
        log_error("guardar_supabase", str(e))
        print(f"[supabase] Error guardando estado: {e}")

# ============================================================
# UTILIDADES
# ============================================================
def get_estado(clave):
    with _lock_estado:
        return _estado.get(clave)

def set_estado(clave, valor):
    with _lock_estado:
        _estado[clave] = valor

def esta_en_blacklist(simbolo: str) -> bool:
    with _lock_estado:
        ts_desbloqueo = _estado["blacklist"].get(simbolo, 0)
        if time.time() < ts_desbloqueo:
            return True
        if simbolo in _estado["blacklist"]:
            del _estado["blacklist"][simbolo]
        return False

def agregar_blacklist(simbolo: str, horas: float = 4.0):
    with _lock_estado:
        _estado["blacklist"][simbolo] = time.time() + (horas * 3600)
        print(f"[blacklist] {simbolo} bloqueado por {horas}h")
    enviar_mensaje(f"🚫 <b>{simbolo} bloqueado</b> — 2 pérdidas consecutivas — pausa {horas}h")

def registrar_resultado(simbolo: str, ganancia: bool) -> bool:
    with _lock_estado:
        if ganancia:
            _estado["perdidas_consecutivas"][simbolo] = 0
        else:
            actual = _estado["perdidas_consecutivas"].get(simbolo, 0) + 1
            _estado["perdidas_consecutivas"][simbolo] = actual
            if actual >= 2:
                return True
    return False

def evaluar_modo_conservador():
    hora_utc    = datetime.now(timezone.utc).hour
    conservador = hora_utc < 8
    anterior    = get_estado("modo_conservador")

    if conservador != anterior:
        set_estado("modo_conservador", conservador)
        if conservador:
            print(f"[modo] 🌙 Modo CONSERVADOR activado — hora UTC={hora_utc}")
            enviar_mensaje(
                f"🌙 <b>Modo conservador activado</b>\n"
                f"Hora UTC: {hora_utc:02d}:00\n"
                f"Posiciones reducidas al 50%\n"
                f"Umbral confianza: 88% mínimo\n"
                f"Votos requeridos: 3 de 3"
            )
        else:
            print(f"[modo] ☀️ Modo NORMAL activado — hora UTC={hora_utc}")
            enviar_mensaje(
                f"☀️ <b>Modo normal activado</b>\n"
                f"Hora UTC: {hora_utc:02d}:00\n"
                f"Parámetros normales restaurados"
            )
    return conservador

def evaluar_reset_volatilidad():
    with _lock_estado:
        if not _estado["volatilidad_alta"]:
            return
        if _estado.get("volatilidad_alta_origen") != "spike":
            return
        ts_activacion = _estado.get("volatilidad_alta_ts", 0)
        if ts_activacion > 0 and (time.time() - ts_activacion) > TTL_VOLATILIDAD_ALTA:
            _estado["volatilidad_alta"]        = False
            _estado["volatilidad_alta_ts"]     = 0
            _estado["volatilidad_alta_origen"] = ""
            print(f"[volatilidad] Reset automático — modo normal restaurado")
            enviar_mensaje(
                f"✅ <b>Volatilidad normalizada</b>\n"
                f"Sistema restaurado a modo normal\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )

def calcular_cantidad_por_confianza(confianza: float, precio: float, stop_loss: float) -> float:
    portafolio  = obtener_portafolio()
    capital     = portafolio.get("capital_total", 100000)
    conservador = get_estado("modo_conservador")

    if confianza >= 95:   pct_riesgo = 0.015
    elif confianza >= 90: pct_riesgo = 0.012
    elif confianza >= 85: pct_riesgo = 0.010
    else:                 pct_riesgo = 0.005

    if conservador:
        pct_riesgo *= 0.5

    riesgo_usd   = capital * pct_riesgo
    distancia_sl = abs(precio - stop_loss)
    if distancia_sl == 0:
        return 0
    cantidad = riesgo_usd / distancia_sl
    if cantidad * precio > capital * 0.20:
        cantidad = (capital * 0.20) / precio
    return round(cantidad, 6)

def calcular_atr_multiplier() -> float:
    fg          = get_estado("fear_greed") or 50
    conservador = get_estado("modo_conservador")

    if fg < 20:   mult = 3.5
    elif fg < 35: mult = 3.0
    elif fg > 75: mult = 3.0
    else:         mult = 2.5

    if conservador:
        mult += 0.5
    return mult

def obtener_parametros_ejecucion() -> dict:
    conservador = get_estado("modo_conservador")
    return {
        "confianza_minima": 88 if conservador else 80,
        "votos_minimos":    3  if conservador else 2,
        "conservador":      conservador,
    }

def obtener_info_modo() -> dict:
    hora_utc    = datetime.now(timezone.utc).hour
    conservador = get_estado("modo_conservador")
    vol_alta    = get_estado("volatilidad_alta")
    pausado     = get_estado("sistema_pausado")

    if conservador:
        horas_restantes  = 8 - hora_utc if hora_utc < 8 else 0
        siguiente_cambio = f"Modo normal en {horas_restantes}h (08:00 UTC)"
    else:
        horas_hasta_noche = 24 - hora_utc if hora_utc >= 8 else 0
        siguiente_cambio  = f"Modo conservador en {horas_hasta_noche}h (00:00 UTC)"

    return {
        "conservador":      conservador,
        "volatilidad_alta": vol_alta,
        "pausado":          pausado,
        "hora_utc":         hora_utc,
        "siguiente_cambio": siguiente_cambio,
        "confianza_minima": 88 if conservador else 80,
        "votos_minimos":    3  if conservador else 2,
        "tamaño_posicion":  "50%" if conservador else "100%",
        "atr_multiplier":   calcular_atr_multiplier(),
    }

# ============================================================
# MONITOR DE VOLATILIDAD EXTREMA
# ============================================================
async def monitorear_volatilidad(ind_res: list):
    try:
        with _lock_estado:
            precios_ant = dict(_estado["precios_anteriores"])

        alertas_vol    = []
        nuevos_precios = {}

        for ind in ind_res:
            simbolo = ind.get("simbolo", "")
            precio  = ind.get("precio", 0)
            if not precio or not simbolo:
                continue
            nuevos_precios[simbolo] = precio

            if simbolo in precios_ant and precios_ant[simbolo] > 0:
                cambio_pct = ((precio - precios_ant[simbolo]) / precios_ant[simbolo]) * 100
                if abs(cambio_pct) >= UMBRAL_VOLATILIDAD:
                    alertas_vol.append({
                        "simbolo":    simbolo,
                        "cambio_pct": round(cambio_pct, 2),
                        "precio":     precio,
                        "direccion":  "📈 SUBIDA" if cambio_pct > 0 else "📉 BAJADA",
                    })

        with _lock_estado:
            _estado["precios_anteriores"].update(nuevos_precios)

        for alerta in alertas_vol:
            print(f"[volatilidad] ⚡ {alerta['simbolo']} movió {alerta['cambio_pct']:+.2f}% en 15min")
            enviar_mensaje(
                f"⚡ <b>VOLATILIDAD EXTREMA</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{alerta['direccion']} {alerta['simbolo']}\n"
                f"Movimiento: {alerta['cambio_pct']:+.2f}% en 15min\n"
                f"Precio actual: ${alerta['precio']:,.4f}\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ Revisa posiciones abiertas\n"
                f"Usa /posiciones para ver tu exposición"
            )

            if abs(alerta["cambio_pct"]) >= 5.0:
                with _lock_estado:
                    _estado["volatilidad_alta"]        = True
                    _estado["volatilidad_alta_ts"]     = time.time()
                    _estado["volatilidad_alta_origen"] = "spike"
                enviar_mensaje(
                    f"🚨 <b>ALERTA CRÍTICA</b> — {alerta['simbolo']} movió {alerta['cambio_pct']:+.2f}%\n"
                    f"Sistema en modo ultra-conservador por 30 minutos\n"
                    f"Reset automático en 30min"
                )

    except Exception as e:
        log_error("monitorear_volatilidad", str(e))
        print(f"[volatilidad] Error: {e}")

# ============================================================
# AGENTE BALLENAS
# ============================================================
async def monitorear_ballenas():
    try:
        import requests
        señales_ballenas = []

        for simbolo in ["BTCUSDT", "ETHUSDT"]:
            try:
                r = requests.get(
                    "https://api.binance.com/api/v3/depth",
                    params={"symbol": simbolo, "limit": 20},
                    timeout=10
                )
                if r.status_code != 200:
                    continue

                data     = r.json()
                vol_bids = sum(float(b[1]) for b in data.get("bids", []))
                vol_asks = sum(float(a[1]) for a in data.get("asks", []))
                total    = vol_bids + vol_asks
                if total == 0:
                    continue

                ratio_compra = vol_bids / total * 100

                if ratio_compra > 70:
                    señales_ballenas.append({
                        "simbolo": simbolo,
                        "señal":   "COMPRAR",
                        "razon":   f"Order book {ratio_compra:.1f}% compras — acumulación ballena",
                        "fuerza":  "alta" if ratio_compra > 80 else "media",
                    })
                    print(f"[ballenas] {simbolo}: acumulación {ratio_compra:.1f}%")
                elif ratio_compra < 30:
                    señales_ballenas.append({
                        "simbolo": simbolo,
                        "señal":   "VENDER",
                        "razon":   f"Order book {100-ratio_compra:.1f}% ventas — distribución ballena",
                        "fuerza":  "alta" if ratio_compra < 20 else "media",
                    })
                    print(f"[ballenas] {simbolo}: distribución {100-ratio_compra:.1f}%")

            except Exception as e:
                log_error("ballenas", f"{simbolo}: {e}")

        if señales_ballenas:
            compras = sum(1 for s in señales_ballenas if s["señal"] == "COMPRAR")
            ventas  = sum(1 for s in señales_ballenas if s["señal"] == "VENDER")
            señal   = "COMPRAR" if compras > ventas else ("VENDER" if ventas > compras else "ESPERAR")
            set_estado("ballenas_señal", señal)
            set_estado("ballenas_ts", time.time())

            for s in [x for x in señales_ballenas if x["fuerza"] == "alta"]:
                enviar_mensaje(
                    f"🐋 <b>Movimiento de ballena detectado</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"Activo: {s['simbolo']}\n"
                    f"Señal: {s['señal']}\n"
                    f"📊 {s['razon']}"
                )
        else:
            set_estado("ballenas_señal", "ESPERAR")

    except Exception as e:
        log_error("ballenas_general", str(e))
        print(f"[ballenas] Error general: {e}")

# ============================================================
# LOOP 4H — CONTEXTO MACRO + NOTICIAS RSS
# ============================================================
async def loop_4h():
    while True:
        with _lock_estado:
            _estado["ciclo_4h"] += 1
            ciclo = _estado["ciclo_4h"]

        print(f"\n{'='*60}")
        print(f"[4H] CICLO MACRO #{ciclo} — {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*60}")

        try:
            from agente_financiero.agente_google_trends import ejecutar_google_trends
            from agente_financiero.agente_estacionalidad import analizar_estacionalidad_completo
            from agente_financiero.agente_historico import analizar_historico_completo
            from agente_financiero.agente_fundamental import analizar_fundamental_completo
            from agente_financiero.agente_noticias_rss import ejecutar_agente_noticias

            resultados = await asyncio.gather(
                asyncio.wait_for(asyncio.to_thread(ejecutar_google_trends), timeout=120),
                asyncio.to_thread(analizar_estacionalidad_completo),
                analizar_historico_completo(),
                analizar_fundamental_completo(),
                asyncio.to_thread(ejecutar_agente_noticias),
                return_exceptions=True
            )

            trends   = resultados[0] if not isinstance(resultados[0], Exception) else []
            estac    = resultados[1] if not isinstance(resultados[1], Exception) else {}
            hist     = resultados[2] if not isinstance(resultados[2], Exception) else {}
            fund     = resultados[3] if not isinstance(resultados[3], Exception) else {}
            noticias = resultados[4] if not isinstance(resultados[4], Exception) else []

            for nombre, res in [("trends", resultados[0]), ("estac", resultados[1]),
                                 ("hist", resultados[2]), ("fund", resultados[3]),
                                 ("noticias", resultados[4])]:
                if isinstance(res, Exception):
                    log_error(f"loop_4h_{nombre}", str(res))
                    print(f"[4H] Error en {nombre}: {res}")

            estac_señal = estac.get("señal_estacional", "NEUTRAL") if isinstance(estac, dict) else "NEUTRAL"
            estac_conf  = estac.get("confianza", 50) if isinstance(estac, dict) else 50

            alertas_noticias = [n for n in noticias if isinstance(n, dict) and n.get("impacto", 0) >= 6]
            for alerta in alertas_noticias:
                emoji = "🟢" if alerta.get("señal") == "COMPRAR" else "🔴"
                enviar_mensaje(
                    f"📰 <b>NOTICIA ALTO IMPACTO</b> {emoji}\n"
                    f"Activo: {alerta.get('simbolo', 'N/A')}\n"
                    f"Señal: {alerta.get('señal', 'N/A')}\n"
                    f"📌 {alerta.get('titulo_top', 'Sin título')}\n"
                    f"Fuente: {alerta.get('fuente_top', 'N/A')}\n"
                    f"Impacto: {alerta.get('impacto', 0)}/10"
                )

            noticias_con_señal = [n for n in noticias if isinstance(n, dict) and n.get("señal") != "ESPERAR"]
            print(f"[4H] Noticias: {len(noticias)} activos | {len(noticias_con_señal)} con señal | {len(alertas_noticias)} alto impacto")

            with _lock_estado:
                _estado["estac_señal"]      = estac_señal
                _estado["noticias_alertas"] = alertas_noticias
                _estado["contexto_macro"]   = {
                    "trends":      trends,
                    "estacional":  estac,
                    "historico":   hist.get("analisis", "") if isinstance(hist, dict) else "",
                    "fundamental": fund.get("analisis", "") if isinstance(fund, dict) else "",
                    "noticias":    noticias,
                }
                _estado["contexto_ts"] = time.time()

            print(f"[4H] Estac={estac_señal} ({estac_conf}%)")
            enviar_mensaje(
                f"📊 <b>Contexto macro actualizado</b>\n"
                f"Estacionalidad: {estac_señal} ({estac_conf}%)\n"
                f"Noticias relevantes: {len(noticias_con_señal)}\n"
                f"Hora: {datetime.now().strftime('%H:%M:%S')}"
            )

        except asyncio.TimeoutError:
            log_error("loop_4h", "Timeout")
            print(f"[4H] Timeout — continuando con datos parciales")
        except Exception as e:
            log_error("loop_4h", str(e))
            print(f"[4H] Error: {e}")
            enviar_mensaje(f"⚠️ Error loop 4h: {str(e)[:100]}")

        await asyncio.sleep(4 * 3600)

# ============================================================
# LOOP 1H — SENTIMIENTO, MACRO, DXY Y BALLENAS
# ============================================================
async def loop_1h():
    await asyncio.sleep(30)
    while True:
        with _lock_estado:
            _estado["ciclo_1h"] += 1
            ciclo = _estado["ciclo_1h"]

        print(f"\n[1H] CICLO SENTIMIENTO #{ciclo} — {datetime.now().strftime('%H:%M:%S')}")

        try:
            from agente_financiero.agente_sentimiento import analizar_sentimiento_mercado
            from agente_financiero.agente_macro import analizar_contexto_macro
            from agente_financiero.agente_petroleo import analizar_petroleo_completo
            from agente_financiero.agente_opciones import analizar_opciones_completo
            from agente_financiero.agente_correlacion_dxy import analizar_correlacion_dxy

            sent, macro, petro, opciones, dxy = await asyncio.gather(
                analizar_sentimiento_mercado(),
                analizar_contexto_macro(),
                analizar_petroleo_completo(),
                asyncio.to_thread(analizar_opciones_completo),
                asyncio.to_thread(analizar_correlacion_dxy),
                return_exceptions=True
            )

            if isinstance(sent,     Exception): sent    = {}; log_error("loop_1h_sent", str(sent))
            if isinstance(macro,    Exception): macro   = {}; log_error("loop_1h_macro", str(macro))
            if isinstance(petro,    Exception): petro   = {}; log_error("loop_1h_petro", str(petro))
            if isinstance(opciones, Exception): opciones= []; log_error("loop_1h_opciones", str(opciones))
            if isinstance(dxy,      Exception): dxy     = {"señal": "ESPERAR", "error": True}

            fg_valor       = sent.get("fear_greed", {}).get("valor_hoy", 50) if isinstance(sent, dict) else 50
            wti            = petro.get("precios", {}).get("WTI", {}).get("precio", 0) if isinstance(petro, dict) else 0
            wti_cambio     = petro.get("precios", {}).get("WTI", {}).get("cambio_dia", 0) if isinstance(petro, dict) else 0
            opciones_lista = opciones if isinstance(opciones, list) else []
            opciones_btc   = next((o for o in opciones_lista if o.get("moneda") == "BTC"), {})
            pcr_btc        = opciones_btc.get("pcr_volumen", 1.0)
            opciones_señal = opciones_btc.get("señal", "ESPERAR")
            estac_señal    = get_estado("estac_señal") or "NEUTRAL"

            dxy_señal     = dxy.get("señal", "ESPERAR") if isinstance(dxy, dict) else "ESPERAR"
            dxy_actual    = dxy.get("dxy_actual", 0) if isinstance(dxy, dict) else 0
            dxy_cambio_1h = dxy.get("dxy_cambio_1h", 0) if isinstance(dxy, dict) else 0
            correlacion   = dxy.get("correlacion", 0) if isinstance(dxy, dict) else 0

            print(f"[1H] DXY={dxy_actual:.2f} ({dxy_cambio_1h:+.2f}% 1h) | Corr={correlacion:.2f} | Señal={dxy_señal}")

            print(f"[1H] Monitoreando ballenas...")
            await monitorear_ballenas()
            ballenas_señal = get_estado("ballenas_señal") or "ESPERAR"
            print(f"[1H] Ballenas: {ballenas_señal}")

            noticias_alertas = get_estado("noticias_alertas") or []
            noticias_compra  = sum(1 for n in noticias_alertas if n.get("señal") == "COMPRAR")
            noticias_venta   = sum(1 for n in noticias_alertas if n.get("señal") == "VENDER")

            puntos_alcista = sum([
                fg_valor > 60,
                fg_valor > 50 and fg_valor <= 60,
                wti_cambio < -2,
                "ALCISTA" in estac_señal,
                opciones_señal == "COMPRAR",
                noticias_compra > noticias_venta,
                dxy_señal == "COMPRAR",
                ballenas_señal == "COMPRAR",
            ])
            puntos_bajista = sum([
                fg_valor < 40,
                fg_valor >= 40 and fg_valor < 50,
                wti_cambio > 2,
                "BAJISTA" in estac_señal,
                opciones_señal == "VENDER",
                noticias_venta > noticias_compra,
                dxy_señal == "VENDER",
                ballenas_señal == "VENDER",
            ])

            sesgo         = "ALCISTA" if puntos_alcista > puntos_bajista else (
                            "BAJISTA" if puntos_bajista > puntos_alcista else "NEUTRAL")
            confianza_ctx = min(50 + max(puntos_alcista, puntos_bajista) * 10, 85)

            fg_extremo = fg_valor < 25 or fg_valor > 80
            with _lock_estado:
                origen_actual = _estado.get("volatilidad_alta_origen", "")
                if origen_actual != "spike":
                    if fg_extremo:
                        _estado["volatilidad_alta"]        = True
                        _estado["volatilidad_alta_origen"] = "fear_greed"
                    else:
                        _estado["volatilidad_alta"]        = False
                        _estado["volatilidad_alta_origen"] = ""

                _estado["sesgo_contexto"]     = sesgo
                _estado["confianza_contexto"] = confianza_ctx
                _estado["fear_greed"]         = fg_valor
                _estado["wti_precio"]         = wti
                _estado["pcr_btc"]            = pcr_btc
                _estado["dxy_señal"]          = dxy_señal
                _estado["dxy_datos"]          = dxy if isinstance(dxy, dict) else {}

            print(f"[1H] F&G={fg_valor} | Sesgo={sesgo} ({confianza_ctx}%) | WTI=${wti} | PCR={pcr_btc} | DXY={dxy_señal} | Ballenas={ballenas_señal}")

        except Exception as e:
            log_error("loop_1h", str(e))
            print(f"[1H] Error: {e}")

        await asyncio.sleep(3600)

# ============================================================
# LOOP 15MIN — ANÁLISIS TÉCNICO COMPLETO
# ============================================================
async def loop_15m():
    await asyncio.sleep(60)
    while True:
        with _lock_estado:
            _estado["ciclo_15m"] += 1
            ciclo = _estado["ciclo_15m"]

        print(f"\n{'='*60}")
        print(f"[15M] CICLO TECNICO #{ciclo} — {datetime.now().strftime('%H:%M:%S')}")
        print(f"{'='*60}")

        if get_estado("sistema_pausado"):
            print(f"[15M] Sistema pausado manualmente — saltando ciclo")
            await asyncio.sleep(15 * 60)
            continue

        try:
            horario = debe_operar()
            if not horario["operar"]:
                print(f"[15M] Fuera de horario — {horario['razon']}")
                await asyncio.sleep(15 * 60)
                continue

            sesgo_ctx = get_estado("sesgo_contexto") or "NEUTRAL"
            atr_mult  = calcular_atr_multiplier()
            sesion    = obtener_sesion_actual()
            score     = sesion.get("score_sesion", 5)
            max_ops   = 3 if score >= 10 else (2 if score >= 7 else 1)

            resultado = await ejecutar_ciclo_maestro()

            tabla_maestra = resultado.get("tabla_maestra", [])
            señales_f     = resultado.get("señales_fuertes", [])
            señales       = resultado.get("señales_aprobadas", [])
            ordenes_e     = resultado.get("ordenes_ejecutadas", [])

            if resultado.get("operar", True):
                with _lock_estado:
                    _estado["tabla_maestra"]   = tabla_maestra
                    _estado["señales_fuertes"] = señales_f
                    _estado["tabla_ts"]        = time.time()

                print(f"[15M] Señales={len(señales)} | Ordenes={len(ordenes_e)} | ATR={atr_mult}x | MaxOps={max_ops} | Sesgo={sesgo_ctx}")

                for orden in ordenes_e:
                    if "error" not in orden:
                        enviar_mensaje(
                            f"✅ <b>Orden ejecutada</b> ciclo #{ciclo}\n"
                            f"Símbolo: {orden.get('simbolo')}\n"
                            f"Acción: {orden.get('accion')}\n"
                            f"Precio: ${orden.get('precio')}\n"
                            f"Sesgo macro: {sesgo_ctx}"
                        )

                if ciclo % 4 == 0:
                    stats = obtener_estadisticas_dia()
                    alerta_resumen_dia(stats)

            if es_horario_mercado():
                print(f"[15M] NYSE abierto — analizando acciones...")
                try:
                    res_acc     = await ejecutar_ciclo_acciones()
                    señales_acc = res_acc.get("señales_fuertes", [])
                    if señales_acc:
                        enviar_mensaje(
                            "📈 <b>SEÑALES ACCIONES USA</b>\n" + "\n".join([
                                f"{s['simbolo']}: {s['señal_final']} | conf={s['confianza']}% | ${s['precio']}"
                                for s in señales_acc
                            ])
                        )
                except Exception as e:
                    log_error("loop_15m_acciones", str(e))
                    print(f"[15M] Error acciones: {e}")

        except Exception as e:
            log_error("loop_15m", str(e))
            print(f"[15M] Error ciclo #{ciclo}: {e}")
            enviar_mensaje(f"⚠️ Error loop 15m #{ciclo}: {str(e)[:100]}")

        if ciclo % 480 == 0:
            try:
                sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
                sb.table("señales_trading").select("id").limit(1).execute()
                print("[15M] Ping Supabase OK")
            except Exception as e:
                log_error("ping_supabase", str(e))
                print(f"[15M] Ping Supabase error: {e}")

        await asyncio.sleep(15 * 60)

# ============================================================
# LOOP 2MIN — SEÑALES URGENTES, EJECUCIÓN Y PROTECCIÓN
# ============================================================
async def loop_2m():
    await asyncio.sleep(120)
    while True:
        with _lock_estado:
            _estado["ciclo_2m"] += 1
            ciclo = _estado["ciclo_2m"]

        try:
            # Pausa manual — guarda estado antes de saltar
            if get_estado("sistema_pausado"):
                await guardar_estado_supabase()
                await asyncio.sleep(2 * 60)
                continue

            # Fuera de horario — guarda estado antes de saltar
            horario = debe_operar()
            if not horario["operar"]:
                await guardar_estado_supabase()
                await asyncio.sleep(2 * 60)
                continue

            evaluar_reset_volatilidad()
            conservador    = evaluar_modo_conservador()
            params         = obtener_parametros_ejecucion()
            sesgo_ctx      = get_estado("sesgo_contexto") or "NEUTRAL"
            atr_mult       = calcular_atr_multiplier()
            dxy_señal      = get_estado("dxy_señal") or "ESPERAR"
            ballenas_señal = get_estado("ballenas_señal") or "ESPERAR"
            vol_alta       = get_estado("volatilidad_alta")

            modo_txt = "🌙 CONSERVADOR" if conservador else "☀️ NORMAL"
            vol_txt  = " | 🚨 VOL_ALTA" if vol_alta else ""
            print(f"[2M] Ciclo #{ciclo} — {datetime.now().strftime('%H:%M:%S')} | {modo_txt}{vol_txt} | Sesgo={sesgo_ctx} | DXY={dxy_señal} | 🐋={ballenas_señal}")

            try:
                cerradas = await asyncio.to_thread(monitorear_perdidas_excesivas)
                for c in cerradas:
                    print(f"[2M] ⛔ Cierre forzado {c['simbolo']} — pérdida {c['pnl_pct']:.2f}%")
                    enviar_mensaje(
                        f"⛔ <b>Cierre automático</b>\n"
                        f"Símbolo: {c['simbolo']}\n"
                        f"Pérdida: {c['pnl_pct']:.2f}% (${c['pnl_usd']:.2f})\n"
                        f"Razón: supera límite del 5%"
                    )
                    if registrar_resultado(c['simbolo'], False):
                        agregar_blacklist(c['simbolo'])
            except Exception as e:
                log_error("monitor_perdidas", str(e))
                print(f"[2M] Error monitor pérdidas: {e}")

            try:
                await asyncio.to_thread(monitorear_y_ejecutar_trailing)
            except Exception as e:
                log_error("trailing", str(e))
                print(f"[2M] Error trailing: {e}")

            velas_res, ind_res, of_res, fund_res = await asyncio.gather(
                analizar_oportunidades(),
                asyncio.to_thread(analizar_indicadores_completo),
                asyncio.to_thread(analizar_todos_activos, ACTIVOS_CRYPTO),
                asyncio.to_thread(analizar_funding_completo),
                return_exceptions=True
            )

            if isinstance(velas_res, Exception):
                log_error("loop_2m_velas", str(velas_res))
                velas_res = {"oportunidades": [], "alertas": []}
            if isinstance(ind_res,   Exception):
                log_error("loop_2m_indicadores", str(ind_res))
                ind_res   = []
            if isinstance(of_res,    Exception):
                log_error("loop_2m_orderflow", str(of_res))
                of_res    = []
            if isinstance(fund_res,  Exception):
                log_error("loop_2m_funding", str(fund_res))
                fund_res  = []

            if ind_res:
                await monitorear_volatilidad(ind_res)

            posiciones_abiertas = obtener_posiciones()

            for ind in ind_res:
                simbolo   = ind["simbolo"]
                señal_ind = ind["señal"]
                confianza = ind["confianza"]
                precio    = ind["precio"]
                atr       = ind.get("atr", {})

                if not atr or not atr.get("atr"):
                    continue
                if esta_en_blacklist(simbolo):
                    continue
                if any(simbolo in p["simbolo"] for p in posiciones_abiertas):
                    continue
                if get_estado("volatilidad_alta") and confianza < 95:
                    print(f"[2M] {simbolo} pausado — volatilidad extrema activa")
                    continue

                vela_op     = next((o for o in velas_res["oportunidades"] if simbolo in o["simbolo"]), None)
                vela_alerta = next((a for a in velas_res["alertas"]       if simbolo in a["simbolo"]), None)
                señal_velas = "COMPRAR" if vela_op else ("VENDER" if vela_alerta else "NEUTRAL")

                of       = next((o for o in of_res  if o.get("simbolo") == simbolo), {})
                señal_of = "COMPRAR" if "COMPRADORA" in of.get("señal","") else (
                           "VENDER"  if "VENDEDORA"  in of.get("señal","") else "NEUTRAL")

                fund       = next((f for f in fund_res if f.get("simbolo") == simbolo), {})
                señal_fund = fund.get("accion", "ESPERAR")

                noticias_alertas = get_estado("noticias_alertas") or []
                noticia_alineada = next(
                    (n for n in noticias_alertas
                     if simbolo in n.get("simbolo", "") and n.get("señal") == señal_ind),
                    None
                )
                boost_noticia = 5 if noticia_alineada else 0

                boost_dxy = 0
                if simbolo == "BTCUSDT" and dxy_señal == señal_ind and dxy_señal != "ESPERAR":
                    boost_dxy = 5

                boost_ballenas = 0
                if simbolo in ["BTCUSDT", "ETHUSDT"] and ballenas_señal == señal_ind and ballenas_señal != "ESPERAR":
                    boost_ballenas = 5

                votos = sum([
                    señal_velas == señal_ind and señal_ind != "ESPERAR",
                    señal_of    == señal_ind and señal_ind != "ESPERAR",
                    señal_fund  == señal_ind and señal_ind != "ESPERAR",
                ])

                if votos < params["votos_minimos"] or confianza < params["confianza_minima"]:
                    continue
                if sesgo_ctx == "BAJISTA" and señal_ind == "COMPRAR":
                    continue
                if sesgo_ctx == "ALCISTA" and señal_ind == "VENDER":
                    continue

                if señal_ind == "COMPRAR":
                    sl  = round(precio - (atr["atr"] * atr_mult), 4)
                    tp1 = round(precio + (atr["atr"] * atr_mult * 2), 4)
                else:
                    sl  = round(precio + (atr["atr"] * atr_mult), 4)
                    tp1 = round(precio - (atr["atr"] * atr_mult * 2), 4)

                cantidad = calcular_cantidad_por_confianza(confianza, precio, sl)
                if cantidad <= 0:
                    continue

                confianza_final = min(confianza + (votos * 5) + boost_noticia + boost_dxy + boost_ballenas, 99)
                extras = []
                if noticia_alineada:   extras.append(f"📰 {noticia_alineada['titulo_top'][:40]}")
                if boost_dxy > 0:      extras.append("💵 DXY confirma")
                if boost_ballenas > 0: extras.append("🐋 Ballenas confirman")
                if conservador:        extras.append("🌙 modo conservador")
                razon_extra = " | " + " | ".join(extras) if extras else ""

                print(f"[2M] SEÑAL: {simbolo} {señal_ind} conf={confianza_final}% votos={votos}{' +DXY' if boost_dxy else ''}{' +ballenas' if boost_ballenas else ''}{' +noticia' if boost_noticia else ''}{' 🌙' if conservador else ''}")

                orden = ejecutar_orden(
                    simbolo=simbolo, accion=señal_ind,
                    cantidad=cantidad, precio_entrada=precio,
                    stop_loss=sl, take_profit=tp1,
                    atr=atr.get("atr_pct", 0)
                )

                if "error" not in orden:
                    alerta_señal(
                        simbolo=simbolo, accion=señal_ind,
                        precio=precio, sl=sl, tp1=tp1,
                        confianza=confianza_final,
                        razon=f"Loop 2m — {votos} fuentes | ATR {atr_mult}x | {sesgo_ctx}{razon_extra}",
                        horizonte="2min"
                    )
                    if registrar_resultado(simbolo, False):
                        agregar_blacklist(simbolo)
                else:
                    log_error("ejecutar_orden", f"{simbolo}: {orden.get('error')}")
                    print(f"[2M] Error orden {simbolo}: {orden.get('error')}")

        except Exception as e:
            log_error("loop_2m", str(e))
            print(f"[2M] Error: {e}")

        # Guarda estado en Supabase cada ciclo para el dashboard
        await guardar_estado_supabase()
        await asyncio.sleep(2 * 60)

# ============================================================
# MAIN
# ============================================================
async def main():
    print(f"\n{'='*60}")
    print(f"SISTEMA DE TRADING IA — ARQUITECTURA MULTI-LOOP")
    print(f"Loop 4h: macro + noticias | Loop 1h: sentimiento + DXY + ballenas")
    print(f"Loop 15m: tecnico | Loop 2m: ejecucion + proteccion + volatilidad")
    print(f"{'='*60}")

    enviado = enviar_mensaje(
        f"🤖 <b>Sistema Trading IA iniciado</b>\n"
        f"Arquitectura: 4h | 1h | 15m | 2m\n"
        f"Noticias RSS + DXY + Ballenas activos\n"
        f"Alertas volatilidad >3% + Reset automático 30min\n"
        f"Rate limiter Claude 20/hora activo\n"
        f"Dashboard Supabase activo\n"
        f"Hora: {datetime.now().strftime('%H:%M:%S')}"
    )
    print(f"[main] Telegram: {'OK' if enviado else 'ERROR'}")

    await asyncio.gather(
        loop_4h(),
        loop_1h(),
        loop_15m(),
        loop_2m(),
        escuchar_comandos(),
    )

if __name__ == "__main__":
    asyncio.run(main())