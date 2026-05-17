# agente_financiero/trailing_stop.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from datetime import datetime
from agente_financiero.cache_mercado import obtener_precio_actual
from agente_financiero.logger_trading import log_cierre

class GestorTrailingStop:
    def __init__(self):
        self.posiciones = {}

    def registrar_posicion(self, simbolo: str, accion: str,
                           precio_entrada: float, cantidad: float,
                           stop_loss: float, take_profit_1: float,
                           take_profit_2: float, atr: float = 0) -> dict:
        posicion = {
            "simbolo":        simbolo,
            "accion":         accion,
            "precio_entrada": precio_entrada,
            "cantidad":       cantidad,
            "stop_loss":      stop_loss,
            "stop_inicial":   stop_loss,
            "take_profit_1":  take_profit_1,
            "take_profit_2":  take_profit_2,
            "atr":            atr,
            "tp1_alcanzado":  False,
            "cantidad_actual": cantidad,
            "breakeven_activado": False,
            "precio_max":     precio_entrada,
            "precio_min":     precio_entrada,
            "apertura":       datetime.now().isoformat(),
            "estado":         "ABIERTA",
        }
        self.posiciones[simbolo] = posicion
        print(f"[trailing] Posicion registrada: {accion} {simbolo} @ {precio_entrada}")
        return posicion

    def actualizar_trailing(self, simbolo: str) -> dict:
        if simbolo not in self.posiciones:
            return {"accion": "NINGUNA"}

        pos    = self.posiciones[simbolo]
        precio = obtener_precio_actual(simbolo)

        if precio == 0:
            return {"accion": "NINGUNA"}

        accion_señal = "MANTENER"
        razon        = ""

        if pos["accion"] == "COMPRAR":
            # Actualiza precio maximo
            if precio > pos["precio_max"]:
                pos["precio_max"] = precio

            # Trailing stop — sigue al precio hacia arriba
            atr = pos.get("atr", 0)
            if atr > 0:
                nuevo_stop = precio - (atr * 2.0)
                if nuevo_stop > pos["stop_loss"]:
                    pos["stop_loss"] = round(nuevo_stop, 4)
                    print(f"[trailing] {simbolo} stop subido a {pos['stop_loss']}")

            # Verifica TP1
            if not pos["tp1_alcanzado"] and precio >= pos["take_profit_1"]:
                pos["tp1_alcanzado"]   = True
                pos["cantidad_actual"] = round(pos["cantidad"] * 0.5, 6)
                pos["breakeven_activado"] = True
                pos["stop_loss"]       = pos["precio_entrada"]  # Mueve stop a breakeven
                accion_señal = "CERRAR_PARCIAL_50"
                razon = f"TP1 alcanzado @ {precio} — cerrando 50%, stop a breakeven"
                print(f"[trailing] {simbolo} TP1 alcanzado — cierre parcial 50%")

            # Verifica TP2
            if pos["tp1_alcanzado"] and precio >= pos["take_profit_2"]:
                accion_señal = "CERRAR_TOTAL"
                razon = f"TP2 alcanzado @ {precio}"
                pos["estado"] = "CERRADA"

            # Verifica stop loss
            if precio <= pos["stop_loss"]:
                if pos["tp1_alcanzado"]:
                    accion_señal = "CERRAR_TOTAL"
                    razon = f"Stop loss en breakeven @ {precio} — ganancia asegurada"
                else:
                    accion_señal = "STOP_LOSS"
                    razon = f"Stop loss tocado @ {precio}"
                pos["estado"] = "CERRADA"

        elif pos["accion"] == "VENDER":
            # Actualiza precio minimo
            if precio < pos["precio_min"]:
                pos["precio_min"] = precio

            # Trailing stop — sigue al precio hacia abajo
            atr = pos.get("atr", 0)
            if atr > 0:
                nuevo_stop = precio + (atr * 2.0)
                if nuevo_stop < pos["stop_loss"]:
                    pos["stop_loss"] = round(nuevo_stop, 4)

            # Verifica TP1
            if not pos["tp1_alcanzado"] and precio <= pos["take_profit_1"]:
                pos["tp1_alcanzado"]   = True
                pos["cantidad_actual"] = round(pos["cantidad"] * 0.5, 6)
                pos["stop_loss"]       = pos["precio_entrada"]
                accion_señal = "CERRAR_PARCIAL_50"
                razon = f"TP1 alcanzado @ {precio}"

            # Verifica TP2
            if pos["tp1_alcanzado"] and precio <= pos["take_profit_2"]:
                accion_señal = "CERRAR_TOTAL"
                razon = f"TP2 alcanzado @ {precio}"
                pos["estado"] = "CERRADA"

            # Verifica stop loss
            if precio >= pos["stop_loss"]:
                accion_señal = "STOP_LOSS"
                razon = f"Stop loss tocado @ {precio}"
                pos["estado"] = "CERRADA"

        # Calcula PnL flotante
        if pos["accion"] == "COMPRAR":
            pnl_pct = round(((precio - pos["precio_entrada"]) / pos["precio_entrada"]) * 100, 3)
        else:
            pnl_pct = round(((pos["precio_entrada"] - precio) / pos["precio_entrada"]) * 100, 3)

        pnl_usd = round(pnl_pct / 100 * pos["precio_entrada"] * pos["cantidad_actual"], 2)

        return {
            "simbolo":      simbolo,
            "accion":       accion_señal,
            "precio_actual": precio,
            "stop_loss":    pos["stop_loss"],
            "pnl_pct":      pnl_pct,
            "pnl_usd":      pnl_usd,
            "razon":        razon,
            "tp1_alcanzado": pos["tp1_alcanzado"],
            "breakeven":    pos["breakeven_activado"],
            "cantidad_actual": pos["cantidad_actual"],
        }

    def monitorear_todas(self) -> list:
        resultados = []
        for simbolo in list(self.posiciones.keys()):
            if self.posiciones[simbolo]["estado"] == "ABIERTA":
                resultado = self.actualizar_trailing(simbolo)
                resultados.append(resultado)
                if resultado["accion"] in ["CERRAR_TOTAL", "STOP_LOSS"]:
                    del self.posiciones[simbolo]
        return resultados

    def resumen_posiciones(self) -> list:
        resumen = []
        for simbolo, pos in self.posiciones.items():
            precio = obtener_precio_actual(simbolo)
            if pos["accion"] == "COMPRAR":
                pnl_pct = round(((precio - pos["precio_entrada"]) / pos["precio_entrada"]) * 100, 3)
            else:
                pnl_pct = round(((pos["precio_entrada"] - precio) / pos["precio_entrada"]) * 100, 3)

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

# Instancia global
gestor_trailing = GestorTrailingStop()