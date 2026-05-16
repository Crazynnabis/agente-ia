# agente_financiero/ejecutor_alpaca.py
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime
from agente_financiero.logger_trading import log_orden, log_cierre
from agente_financiero.alertas_telegram import alerta_orden_ejecutada, alerta_cierre
from agente_financiero.trailing_stop import gestor_trailing

load_dotenv(r'C:\Users\Oscar Hernandez\.env', override=True)

ALPACA_API_KEY    = os.getenv("PKOVTNRRRLBN6EGVUFPIEIXKUM")
ALPACA_API_SECRET = os.getenv("J3R59nxCcqkgmKWvipQPXkFgQ7HeJ59QXAG33ewjha4Z")
ALPACA_URL        = os.getenv("ALPACA_URL", "https://paper-api.alpaca.markets")

# Mapeo de simbolos Binance a Alpaca
SIMBOLO_MAP = {
    "BTCUSDT": "BTC/USD",
    "ETHUSDT": "ETH/USD",
    "SOLUSDT": "SOL/USD",
    "BNBUSDT": "BNB/USD",
    "AAPL":    "AAPL",
    "NVDA":    "NVDA",
    "MSFT":    "MSFT",
    "TSLA":    "TSLA",
    "SPY":     "SPY",
}

def obtener_cliente():
    try:
        from dotenv import load_dotenv
        load_dotenv(r'C:\Users\Oscar Hernandez\.env', override=True)
        key    = os.getenv("ALPACA_API_KEY")
        secret = os.getenv("ALPACA_SECRET_KEY")
        cliente = TradingClient(
            api_key=key,
            secret_key=secret,
            paper=True
        )
        return cliente
    except Exception as e:
        print(f"[alpaca] Error conectando: {e}")
        return None

def obtener_portafolio() -> dict:
    try:
        cliente = obtener_cliente()
        if not cliente:
            return {}
        cuenta = cliente.get_account()
        return {
            "capital_total":  float(cuenta.portfolio_value),
            "cash":           float(cuenta.cash),
            "buying_power":   float(cuenta.buying_power),
            "equity":         float(cuenta.equity),
            "pnl_dia":        float(cuenta.equity) - float(cuenta.last_equity) if cuenta.last_equity else 0,
        }
    except Exception as e:
        print(f"[alpaca] Error portafolio: {e}")
        return {}

def obtener_posiciones() -> list:
    try:
        cliente = obtener_cliente()
        if not cliente:
            return []
        posiciones = cliente.get_all_positions()
        resultado = []
        for p in posiciones:
            resultado.append({
                "simbolo":       p.symbol,
                "cantidad":      float(p.qty),
                "precio_entrada": float(p.avg_entry_price),
                "precio_actual": float(p.current_price),
                "pnl_usd":       float(p.unrealized_pl),
                "pnl_pct":       float(p.unrealized_plpc) * 100,
                "valor_mercado": float(p.market_value),
            })
        return resultado
    except Exception as e:
        print(f"[alpaca] Error posiciones: {e}")
        return []

def ejecutar_orden(simbolo: str, accion: str, cantidad: float,
                   precio_entrada: float, stop_loss: float,
                   take_profit: float, atr: float = 0) -> dict:
    try:
        cliente = obtener_cliente()
        if not cliente:
            return {"error": "Sin conexión a Alpaca"}

        simbolo_alpaca = SIMBOLO_MAP.get(simbolo, simbolo)
        side = OrderSide.BUY if accion == "COMPRAR" else OrderSide.SELL

        print(f"[alpaca] Ejecutando {accion} {cantidad} {simbolo_alpaca}...")

        orden_request = MarketOrderRequest(
            symbol=simbolo_alpaca,
            qty=round(cantidad, 6),
            side=side,
            time_in_force=TimeInForce.GTC,
        )

        orden = cliente.submit_order(orden_request)
        orden_id = str(orden.id)

        print(f"[alpaca] Orden ejecutada: {orden_id}")

        # Registra en logger
        log_orden(
            simbolo=simbolo,
            accion=accion,
            precio=precio_entrada,
            cantidad=cantidad,
            orden_id=orden_id,
            estado="EJECUTADA"
        )

        # Registra en trailing stop
        gestor_trailing.registrar_posicion(
            simbolo=simbolo,
            accion=accion,
            precio_entrada=precio_entrada,
            cantidad=cantidad,
            stop_loss=stop_loss,
            take_profit_1=take_profit,
            take_profit_2=take_profit * 1.5,
            atr=atr
        )

        # Alerta Telegram
        alerta_orden_ejecutada(
            simbolo=simbolo,
            accion=accion,
            precio=precio_entrada,
            cantidad=cantidad,
            valor_usd=cantidad * precio_entrada,
            orden_id=orden_id
        )

        return {
            "orden_id":  orden_id,
            "simbolo":   simbolo,
            "accion":    accion,
            "cantidad":  cantidad,
            "precio":    precio_entrada,
            "estado":    "EJECUTADA",
        }

    except Exception as e:
        print(f"[alpaca] Error ejecutando orden: {e}")
        return {"error": str(e)}

def cerrar_posicion(simbolo: str, razon: str = "señal de cierre") -> dict:
    try:
        cliente = obtener_cliente()
        if not cliente:
            return {"error": "Sin conexión"}

        simbolo_alpaca = SIMBOLO_MAP.get(simbolo, simbolo)
        cliente.close_position(simbolo_alpaca)

        posiciones = obtener_posiciones()
        pos = next((p for p in posiciones if simbolo in p["simbolo"]), None)

        if pos:
            log_cierre(
                simbolo=simbolo,
                precio_entrada=pos["precio_entrada"],
                precio_cierre=pos["precio_actual"],
                cantidad=pos["cantidad"],
                pnl_usd=pos["pnl_usd"],
                razon_cierre=razon
            )
            alerta_cierre(
                simbolo=simbolo,
                precio_entrada=pos["precio_entrada"],
                precio_cierre=pos["precio_actual"],
                pnl_usd=pos["pnl_usd"],
                pnl_pct=pos["pnl_pct"],
                razon=razon
            )

        print(f"[alpaca] Posicion {simbolo} cerrada: {razon}")
        return {"estado": "CERRADA", "simbolo": simbolo}

    except Exception as e:
        print(f"[alpaca] Error cerrando posicion: {e}")
        return {"error": str(e)}

def monitorear_y_ejecutar_trailing() -> list:
    acciones = gestor_trailing.monitorear_todas()
    for accion in acciones:
        if accion["accion"] == "CERRAR_TOTAL":
            cerrar_posicion(accion["simbolo"], "TP2 alcanzado")
        elif accion["accion"] == "STOP_LOSS":
            cerrar_posicion(accion["simbolo"], "Stop loss tocado")
        elif accion["accion"] == "CERRAR_PARCIAL_50":
            print(f"[alpaca] Cierre parcial 50% {accion['simbolo']} — TP1 alcanzado")
    return acciones