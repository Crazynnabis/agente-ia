# loop_automatico.py — Arquitectura de loops anidados por frecuencia
import os
import sys
import asyncio
import time
from threading import Lock

os.environ["DOTENV_PATH"] = r'C:\Users\Oscar Hernandez\.env'
from dotenv import load_dotenv
load_dotenv(r'C:\Users\Oscar Hernandez\.env', override=True)
sys.path.insert(0, r'C:\Users\Oscar Hernandez\agente-ia')

from datetime import datetime
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

ACTIVOS_CRYPTO = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]

# ============================================================
# ESTADO GLOBAL COMPARTIDO ENTRE LOOPS — thread-safe
# ============================================================
_lock_estado = Lock()
_estado = {
    "contexto_macro":        {},
    "contexto_ts":           0,
    "sesgo_contexto":        "NEUTRAL",
    "confianza_contexto":    50,
    "fear_greed":            50,
    "wti_precio":            0,
    "estac_señal":           "NEUTRAL",
    "pcr_btc":               1.0,
    "tabla_maestra":         [],
    "señales_fuertes":       [],
    "tabla_ts":              0,
    "blacklist":             {},
    "perdidas_consecutivas": {},
    "volatilidad_alta":      False,
    "ciclo_4h":              0,
    "ciclo_1h":              0,
    "ciclo_15m":             0,
    "ciclo_2m":              0,
}

gestor = GestorRiesgo()

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

def calcular_cantidad_por_confianza(confianza: float, precio: float, stop_loss: float) -> float:
    portafolio = obtener_portafolio()
    capital    = portafolio.get("capital_total", 100000)
    if confianza >= 95:   pct_riesgo = 0.015
    elif confianza >= 90: pct_riesgo = 0.012
    elif confianza >= 85: pct_riesgo = 0.010
    else:                 pct_riesgo = 0.005
    riesgo_usd   = capital * pct_riesgo
    distancia_sl = abs(precio - stop_loss)
    if distancia_sl == 0:
        return 0
    cantidad = riesgo_usd / distancia_sl
    if cantidad * precio > capital * 0.20:
        cantidad = (capital * 0.20) / precio
    return round(cantidad, 6)

def calcular_atr_multiplier() -> float:
    fg = get_estado("fear_greed") or 50
    if fg < 20:   return 3.5
    elif fg < 35: return 3.0
    elif fg > 75: return 3.0
    else:         return 2.5

# ============================================================
# LOOP 4H — CONTEXTO MACRO
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

            trends, estac, hist, fund = await asyncio.gather(
                asyncio.wait_for(asyncio.to_thread(ejecutar_google_trends), timeout=120),
                asyncio.to_thread(analizar_estacionalidad_completo),
                analizar_historico_completo(),
                analizar_fundamental_completo(),
            )

            estac_señal = estac.get("señal_estacional", "NEUTRAL")
            estac_conf  = estac.get("confianza", 50)

            with _lock_estado:
                _estado["estac_señal"]    = estac_señal
                _estado["contexto_macro"] = {
                    "trends":      trends,
                    "estacional":  estac,
                    "historico":   hist.get("analisis", ""),
                    "fundamental": fund.get("analisis", ""),
                }
                _estado["contexto_ts"] = time.time()

            print(f"[4H] Estac={estac_señal} ({estac_conf}%)")
            enviar_mensaje(
                f"📊 <b>Contexto macro actualizado</b>\n"
                f"Estacionalidad: {estac_señal} ({estac_conf}%)\n"
                f"Hora: {datetime.now().strftime('%H:%M:%S')}"
            )

        except asyncio.TimeoutError:
            print(f"[4H] Google Trends timeout — continuando sin trends")
        except Exception as e:
            print(f"[4H] Error: {e}")
            enviar_mensaje(f"⚠️ Error loop 4h: {str(e)[:100]}")

        await asyncio.sleep(4 * 3600)

# ============================================================
# LOOP 1H — SENTIMIENTO Y MACRO
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

            sent, macro, petro, opciones = await asyncio.gather(
                analizar_sentimiento_mercado(),
                analizar_contexto_macro(),
                analizar_petroleo_completo(),
                asyncio.to_thread(analizar_opciones_completo),
            )

            fg_valor       = sent.get("fear_greed", {}).get("valor_hoy", 50)
            wti            = petro.get("precios", {}).get("WTI", {}).get("precio", 0)
            wti_cambio     = petro.get("precios", {}).get("WTI", {}).get("cambio_dia", 0)
            opciones_btc   = next((o for o in opciones if o.get("moneda") == "BTC"), {})
            pcr_btc        = opciones_btc.get("pcr_volumen", 1.0)
            opciones_señal = opciones_btc.get("señal", "ESPERAR")
            estac_señal    = get_estado("estac_señal") or "NEUTRAL"

            puntos_alcista = sum([fg_valor > 60, fg_valor > 50 and fg_valor <= 60,
                                  wti_cambio < -2, "ALCISTA" in estac_señal, opciones_señal == "COMPRAR"])
            puntos_bajista = sum([fg_valor < 40, fg_valor >= 40 and fg_valor < 50,
                                  wti_cambio > 2, "BAJISTA" in estac_señal, opciones_señal == "VENDER"])

            sesgo         = "ALCISTA" if puntos_alcista > puntos_bajista else (
                            "BAJISTA" if puntos_bajista > puntos_alcista else "NEUTRAL")
            confianza_ctx = min(50 + max(puntos_alcista, puntos_bajista) * 10, 85)

            with _lock_estado:
                _estado["sesgo_contexto"]     = sesgo
                _estado["confianza_contexto"] = confianza_ctx
                _estado["fear_greed"]         = fg_valor
                _estado["wti_precio"]         = wti
                _estado["pcr_btc"]            = pcr_btc
                _estado["volatilidad_alta"]   = fg_valor < 25 or fg_valor > 80

            print(f"[1H] F&G={fg_valor} | Sesgo={sesgo} ({confianza_ctx}%) | WTI=${wti} | PCR={pcr_btc}")

        except Exception as e:
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

            # Acciones NYSE si está abierto
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
                    print(f"[15M] Error acciones: {e}")

        except Exception as e:
            print(f"[15M] Error ciclo #{ciclo}: {e}")
            enviar_mensaje(f"⚠️ Error loop 15m #{ciclo}: {str(e)[:100]}")

        if ciclo % 480 == 0:
            try:
                sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
                sb.table("señales_trading").select("id").limit(1).execute()
                print("[15M] Ping Supabase OK")
            except Exception as e:
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
            horario = debe_operar()
            if not horario["operar"]:
                await asyncio.sleep(2 * 60)
                continue

            sesgo_ctx = get_estado("sesgo_contexto") or "NEUTRAL"
            atr_mult  = calcular_atr_multiplier()

            print(f"[2M] Ciclo #{ciclo} — {datetime.now().strftime('%H:%M:%S')} | Sesgo={sesgo_ctx}")

            # ── Protección de capital ─────────────────────────────
            # Cierre automático si pérdida > 5%
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
                    # Registra como pérdida para blacklist
                    if registrar_resultado(c['simbolo'], False):
                        agregar_blacklist(c['simbolo'])
            except Exception as e:
                print(f"[2M] Error monitor pérdidas: {e}")

            # Trailing stop
            try:
                await asyncio.to_thread(monitorear_y_ejecutar_trailing)
            except Exception as e:
                print(f"[2M] Error trailing: {e}")

            # ── Señales urgentes ──────────────────────────────────
            velas_res, ind_res, of_res, fund_res = await asyncio.gather(
                analizar_oportunidades(),
                asyncio.to_thread(analizar_indicadores_completo),
                asyncio.to_thread(analizar_todos_activos, ACTIVOS_CRYPTO),
                asyncio.to_thread(analizar_funding_completo),
                return_exceptions=True
            )

            # Defaults si algún agente falla
            if isinstance(velas_res, Exception): velas_res = {"oportunidades": [], "alertas": []}
            if isinstance(ind_res,   Exception): ind_res   = []
            if isinstance(of_res,    Exception): of_res    = []
            if isinstance(fund_res,  Exception): fund_res  = []

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

                vela_op     = next((o for o in velas_res["oportunidades"] if simbolo in o["simbolo"]), None)
                vela_alerta = next((a for a in velas_res["alertas"]       if simbolo in a["simbolo"]), None)
                señal_velas = "COMPRAR" if vela_op else ("VENDER" if vela_alerta else "NEUTRAL")

                of         = next((o for o in of_res  if o.get("simbolo") == simbolo), {})
                señal_of   = "COMPRAR" if "COMPRADORA" in of.get("señal","") else (
                             "VENDER"  if "VENDEDORA"  in of.get("señal","") else "NEUTRAL")

                fund       = next((f for f in fund_res if f.get("simbolo") == simbolo), {})
                señal_fund = fund.get("accion", "ESPERAR")

                votos = sum([
                    señal_velas == señal_ind and señal_ind != "ESPERAR",
                    señal_of    == señal_ind and señal_ind != "ESPERAR",
                    señal_fund  == señal_ind and señal_ind != "ESPERAR",
                ])

                if votos < 2 or confianza < 80:
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

                confianza_final = min(confianza + (votos * 5), 99)
                print(f"[2M] SEÑAL: {simbolo} {señal_ind} conf={confianza_final}% votos={votos}")

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
                        razon=f"Loop 2m — {votos} fuentes | ATR {atr_mult}x | {sesgo_ctx}",
                        horizonte="2min"
                    )
                    if registrar_resultado(simbolo, False):
                        agregar_blacklist(simbolo)
                else:
                    print(f"[2M] Error orden {simbolo}: {orden.get('error')}")

        except Exception as e:
            print(f"[2M] Error: {e}")

        await asyncio.sleep(2 * 60)

# ============================================================
# MAIN
# ============================================================
async def main():
    print(f"\n{'='*60}")
    print(f"SISTEMA DE TRADING IA — ARQUITECTURA MULTI-LOOP")
    print(f"Loop 4h: macro | Loop 1h: sentimiento | Loop 15m: tecnico | Loop 2m: ejecucion")
    print(f"{'='*60}")

    enviado = enviar_mensaje(
        f"🤖 <b>Sistema Trading IA iniciado</b>\n"
        f"Arquitectura: 4h | 1h | 15m | 2m\n"
        f"Fallback numérico: activo | Blacklist: activa\n"
        f"Stop loss dinámico + Cierre automático >5%\n"
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