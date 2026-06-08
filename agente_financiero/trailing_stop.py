# agente_financiero/trailing_stop.py
"""
Gestor de trailing stop con persistencia en Supabase.
Sobrevive reinicios de Railway — las posiciones no se pierden.
Soporta crypto (Binance) y acciones USA (Alpaca).
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from agente_financiero.cache_mercado import obtener_precio_actual

SIMBOLOS_ACCIONES = {"AAPL", "NVDA", "MSFT", "TSLA", "SPY", "QQQ", "AMZN", "GOOGL", "META"}

# ============================================================
# PRECIO — crypto via Binance, acciones via Alpaca
# ============================================================
def _obtener_precio(simbolo: str) -> float:
    """Obtiene precio actual según el tipo de activo."""
    # Acciones USA — usar Alpaca
    if simbolo in SIMBOLOS_ACCIONES:
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestTradeRequest
            key    = os.getenv("ALPACA_API_KEY")
            secret = os.getenv("ALPACA_SECRET_KEY")
            if not key or not secret:
                return 0.0
            cliente  = StockHistoricalDataClient(api_key=key, secret_key=secret)
            request  = StockLatestTradeRequest(symbol_or_symbols=simbolo)
            trade    = cliente.get_stock_latest_trade(request)
            return float(trade[simbolo].price)
        except Exception as e:
            print(f"[trailing] Error precio {simbolo} via Alpaca: {e}")
            return 0.0
    # Crypto — usar Binance
    return obtener_precio_actual(simbolo)


# ============================================================
# SUPABASE — persistencia de posiciones
# ============================================================
def _get_supabase():
    try:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if url and key:
            return create_client(url, key)
    except:
        pass
    return None

def _cargar_posiciones_supabase() -> dict:
    """Carga posiciones activas desde Supabase al arrancar."""
    try:
        sb  = _get_supabase()
        if not sb:
            return {}
        res = sb.table("trailing_posiciones").select("*").eq("estado", "ABIERTA").execute()
        posiciones = {}
        for row in res.data:
            simbolo = row["simbolo"]
            posiciones[simbolo] = {
                "simbolo":            simbolo,
                "accion":             row["accion"],
                "precio_entrada":     float(row["precio_entrada"]),
                "cantidad":           float(row["cantidad"]),
                "stop_loss":          float(row["stop_loss"]),
                "stop_inicial":       float(row["stop_inicial"]),
                "take_profit_1":      float(row["take_profit_1"]),
                "take_profit_2":      float(row["take_profit_2"]),
                "atr":                float(row.get("atr", 0) or 0),
                "tp1_alcanzado":      bool(row.get("tp1_alcanzado", False)),
                "cantidad_actual":    float(row.get("cantidad_actual", row["cantidad"])),
                "breakeven_activado": bool(row.get("breakeven_activado", False)),
                "precio_max":         float(row.get("precio_max", row["precio_entrada"])),
                "precio_min":         float(row.get("precio_min", row["precio_entrada"])),
                "apertura":           row.get("apertura", datetime.now().isoformat()),
                "estado":             "ABIERTA",
            }
        if posiciones:
            print(f"[trailing] Restauradas {len(posiciones)} posiciones desde Supabase: {list(posiciones.keys())}")
        return posiciones
    except Exception as e:
        print(f"[trailing] Error cargando posiciones Supabase: {e}")
        return {}

def _guardar_posicion_supabase(pos: dict):
    """Guarda o actualiza una posición en Supabase."""
    try:
        sb = _get_supabase()
        if not sb:
            return
        sb.table("trailing_posiciones").upsert({
            "simbolo":            pos["simbolo"],
            "accion":             pos["accion"],
            "precio_entrada":     pos["precio_entrada"],
            "cantidad":           pos["cantidad"],
            "stop_loss":          pos["stop_loss"],
            "stop_inicial":       pos["stop_inicial"],
            "take_profit_1":      pos["take_profit_1"],
            "take_profit_2":      pos["take_profit_2"],
            "atr":                pos.get("atr", 0),
            "tp1_alcanzado":      pos.get("tp1_alcanzado", False),
            "cantidad_actual":    pos.get("cantidad_actual", pos["cantidad"]),
            "breakeven_activado": pos.get("breakeven_activado", False),
            "precio_max":         pos.get("precio_max", pos["precio_entrada"]),
            "precio_min":         pos.get("precio_min", pos["precio_entrada"]),
            "apertura":           pos.get("apertura", datetime.now().isoformat()),
            "estado":             pos.get("estado", "ABIERTA"),
            "updated_at":         datetime.now().isoformat(),
        }, on_conflict="simbolo").execute()
    except Exception as e:
        print(f"[trailing] Error guardando posicion Supabase: {e}")

def _cerrar_posicion_supabase(simbolo: str, precio_cierre: float, razon: str):
    """Marca una posición como cerrada en Supabase."""
    try:
        sb = _get_supabase()
        if not sb:
            return
        sb.table("trailing_posiciones").update({
            "estado":        "CERRADA",
            "precio_cierre": precio_cierre,
            "razon_cierre":  razon,
            "updated_at":    datetime.now().isoformat(),
        }).eq("simbolo", simbolo).execute()
    except Exception as e:
        print(f"[trailing] Error cerrando posicion Supabase: {e}")


# ============================================================
# GESTOR PRINCIPAL
# ============================================================
class GestorTrailingStop:
    def __init__(self):
        self.posiciones = _cargar_posiciones_supabase()

    def registrar_posicion(self, simbolo: str, accion: str,
                           precio_entrada: float, cantidad: float,
                           stop_loss: float, take_profit_1: float,
                           take_profit_2: float, atr: float = 0) -> dict:
        posicion = {
            "simbolo":            simbolo,
            "accion":             accion,
            "precio_entrada":     precio_entrada,
            "cantidad":           cantidad,
            "stop_loss":          stop_loss,
            "stop_inicial":       stop_loss,
            "take_profit_1":      take_profit_1,
            "take_profit_2":      take_profit_2,
            "atr":                atr,
            "tp1_alcanzado":      False,
            "cantidad_actual":    cantidad,
            "breakeven_activado": False,
            "precio_max":         precio_entrada,
            "precio_min":         precio_entrada,
            "apertura":           datetime.now().isoformat(),
            "estado":             "ABIERTA",
        }
        self.posiciones[simbolo] = posicion
        _guardar_posicion_supabase(posicion)
        print(f"[trailing] Posicion registrada: {accion} {simbolo} @ {precio_entrada}")
        return posicion

    def actualizar_trailing(self, simbolo: str) -> dict:
        if simbolo not in self.posiciones:
            return {"accion": "NINGUNA", "simbolo": simbolo}

        pos    = self.posiciones[simbolo]
        precio = _obtener_precio(simbolo)

        if not precio or precio <= 0:
            return {"accion": "NINGUNA", "simbolo": simbolo}

        accion_senal = "MANTENER"
        razon        = ""
        guardar      = False

        if pos["accion"] == "COMPRAR":
            if precio > pos["precio_max"]:
                pos["precio_max"] = precio
                guardar = True

            atr = pos.get("atr", 0)
            if atr > 0:
                nuevo_stop = precio - (atr * 2.0)
                if nuevo_stop > pos["stop_loss"]:
                    pos["stop_loss"] = round(nuevo_stop, 4)
                    print(f"[trailing] {simbolo} stop subido a {pos['stop_loss']}")
                    guardar = True

            if not pos["tp1_alcanzado"] and precio >= pos["take_profit_1"]:
                pos["tp1_alcanzado"]      = True
                pos["cantidad_actual"]    = round(pos["cantidad"] * 0.5, 6)
                pos["breakeven_activado"] = True
                pos["stop_loss"]          = pos["precio_entrada"]
                accion_senal = "CERRAR_PARCIAL_50"
                razon        = f"TP1 alcanzado @ {precio} — cerrando 50%, stop a breakeven"
                guardar      = True
                print(f"[trailing] {simbolo} TP1 alcanzado — cierre parcial 50%")

            if pos["tp1_alcanzado"] and precio >= pos["take_profit_2"]:
                accion_senal  = "CERRAR_TOTAL"
                razon         = f"TP2 alcanzado @ {precio}"
                pos["estado"] = "CERRADA"
                guardar       = True

            if precio <= pos["stop_loss"]:
                accion_senal  = "CERRAR_TOTAL" if pos["tp1_alcanzado"] else "STOP_LOSS"
                razon         = f"Stop loss tocado @ {precio}"
                pos["estado"] = "CERRADA"
                guardar       = True

        elif pos["accion"] == "VENDER":
            if precio < pos["precio_min"]:
                pos["precio_min"] = precio
                guardar = True

            atr = pos.get("atr", 0)
            if atr > 0:
                nuevo_stop = precio + (atr * 2.0)
                if nuevo_stop < pos["stop_loss"]:
                    pos["stop_loss"] = round(nuevo_stop, 4)
                    guardar = True

            if not pos["tp1_alcanzado"] and precio <= pos["take_profit_1"]:
                pos["tp1_alcanzado"]   = True
                pos["cantidad_actual"] = round(pos["cantidad"] * 0.5, 6)
                pos["stop_loss"]       = pos["precio_entrada"]
                accion_senal = "CERRAR_PARCIAL_50"
                razon        = f"TP1 alcanzado @ {precio}"
                guardar      = True

            if pos["tp1_alcanzado"] and precio <= pos["take_profit_2"]:
                accion_senal  = "CERRAR_TOTAL"
                razon         = f"TP2 alcanzado @ {precio}"
                pos["estado"] = "CERRADA"
                guardar       = True

            if precio >= pos["stop_loss"]:
                accion_senal  = "STOP_LOSS"
                razon         = f"Stop loss tocado @ {precio}"
                pos["estado"] = "CERRADA"
                guardar       = True

        # Guardar en Supabase solo si hubo cambios
        if guardar:
            if pos["estado"] == "CERRADA":
                _cerrar_posicion_supabase(simbolo, precio, razon)
            else:
                _guardar_posicion_supabase(pos)

        # PnL flotante
        if pos["accion"] == "COMPRAR":
            pnl_pct = round(((precio - pos["precio_entrada"]) / pos["precio_entrada"]) * 100, 3)
        else:
            pnl_pct = round(((pos["precio_entrada"] - precio) / pos["precio_entrada"]) * 100, 3)

        pnl_usd = round(pnl_pct / 100 * pos["precio_entrada"] * pos["cantidad_actual"], 2)

        return {
            "simbolo":         simbolo,
            "accion":          accion_senal,
            "precio_actual":   precio,
            "stop_loss":       pos["stop_loss"],
            "pnl_pct":         pnl_pct,
            "pnl_usd":         pnl_usd,
            "razon":           razon,
            "tp1_alcanzado":   pos["tp1_alcanzado"],
            "breakeven":       pos["breakeven_activado"],
            "cantidad_actual": pos["cantidad_actual"],
        }

    def monitorear_todas(self) -> list:
        resultados = []
        for simbolo in list(self.posiciones.keys()):
            if self.posiciones[simbolo]["estado"] == "ABIERTA":
                resultado = self.actualizar_trailing(simbolo)
                resultados.append(resultado)
                if resultado["accion"] in ["CERRAR_TOTAL", "STOP_LOSS"]:
                    if simbolo in self.posiciones:
                        del self.posiciones[simbolo]
        return resultados

    def resumen_posiciones(self) -> list:
        resumen = []
        for simbolo, pos in self.posiciones.items():
            precio = _obtener_precio(simbolo)
            if pos["accion"] == "COMPRAR":
                pnl_pct = round(((precio - pos["precio_entrada"]) / pos["precio_entrada"]) * 100, 3) if precio > 0 else 0
            else:
                pnl_pct = round(((pos["precio_entrada"] - precio) / pos["precio_entrada"]) * 100, 3) if precio > 0 else 0
            resumen.append({
                "simbolo":        simbolo,
                "accion":         pos["accion"],
                "precio_entrada": pos["precio_entrada"],
                "precio_actual":  precio,
                "stop_loss":      pos["stop_loss"],
                "pnl_pct":        pnl_pct,
                "tp1_alcanzado":  pos["tp1_alcanzado"],
                "estado":         pos["estado"],
            })
        return resumen

gestor_trailing = GestorTrailingStop()
