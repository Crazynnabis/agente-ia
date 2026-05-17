# agente_financiero/gestion_riesgo.py
from datetime import datetime, time
import pytz

# Configuracion de riesgo
CONFIG = {
    "capital_total":          100000.0,  # capital paper trading Alpaca
    "riesgo_por_operacion":   0.01,      # 1% maximo por operacion
    "max_operaciones":        2,          # maximo simultaneas
    "max_perdida_diaria":     0.03,       # 3% perdida maxima del dia
    "ratio_minimo_rb":        2.0,        # ratio riesgo/beneficio minimo
    "confianza_minima":       70,         # confianza minima para operar
    "horarios_optimos": [
        (8,  12),  # 8am - 12pm UTC
        (14, 18),  # 2pm - 6pm UTC
    ],
    "zona_horaria": "UTC",
}

class GestorRiesgo:
    def __init__(self, config: dict = None):
        self.config          = config or CONFIG
        self.operaciones_abiertas = []
        self.perdida_diaria  = 0.0
        self.ganancia_diaria = 0.0
        self.operaciones_hoy = []

    def calcular_tamaño_posicion(self, precio: float, stop_loss: float) -> dict:
        try:
            from agente_financiero.kelly_criterion import calcular_tamaño_kelly
            return calcular_tamaño_kelly(precio, stop_loss)
        except Exception as e:
            print(f"[gestion_riesgo] Kelly error: {e} — usando 1% fijo")
            capital      = self.config["capital_total"]
            riesgo_usd   = capital * self.config["riesgo_por_operacion"]
            distancia_sl = abs(precio - stop_loss)
            if distancia_sl == 0:
                return {"error": "Stop loss igual al precio"}
            cantidad       = riesgo_usd / distancia_sl
            valor_posicion = cantidad * precio
            limite         = capital * 0.20
            if valor_posicion > limite:
                cantidad       = limite / precio
                valor_posicion = limite
            return {
                "cantidad":           round(cantidad, 6),
                "valor_posicion_usd": round(valor_posicion, 2),
                "riesgo_usd":         round(riesgo_usd, 2),
                "porcentaje_capital": round((valor_posicion / capital) * 100, 2),
                "distancia_sl_pct":   round((distancia_sl / precio) * 100, 3),
                "fuente":             "fijo_1pct",
            }

    def verificar_horario_optimo(self) -> dict:
        tz    = pytz.timezone(self.config["zona_horaria"])
        ahora = datetime.now(tz).time()
        hora  = ahora.hour

        for inicio, fin in self.config["horarios_optimos"]:
            if inicio <= hora < fin:
                return {
                    "horario_optimo": True,
                    "hora_actual":    hora,
                    "ventana":        f"{inicio}:00 - {fin}:00 UTC",
                }

        return {
            "horario_optimo": False,
            "hora_actual":    hora,
            "mensaje":        f"Hora {hora}:00 UTC fuera de ventana optima. Mejor esperar.",
        }

    def verificar_limites(self) -> dict:
        # Limite de operaciones simultaneas
        if len(self.operaciones_abiertas) >= self.config["max_operaciones"]:
            return {
                "permitido": False,
                "razon":     f"Maximo {self.config['max_operaciones']} operaciones simultaneas alcanzado",
            }

        # Limite de perdida diaria
        capital = self.config["capital_total"]
        if self.perdida_diaria >= capital * self.config["max_perdida_diaria"]:
            return {
                "permitido": False,
                "razon":     f"Perdida diaria maxima alcanzada ({self.config['max_perdida_diaria']*100}%)",
            }

        return {"permitido": True}

    def validar_señal(self, señal: dict) -> dict:
        errores   = []
        warnings  = []

        # Verifica confianza minima
        confianza = señal.get("confianza_final", 0)
        if confianza < self.config["confianza_minima"]:
            errores.append(f"Confianza {confianza}% menor al minimo {self.config['confianza_minima']}%")

        # Verifica ratio R/B
        precio    = señal.get("precio", 0)
        sl        = señal.get("stop_loss", 0)
        tp1       = señal.get("take_profit_1", 0)
        if precio and sl and tp1:
            distancia_sl  = abs(precio - sl)
            distancia_tp1 = abs(tp1 - precio)
            ratio = distancia_tp1 / distancia_sl if distancia_sl > 0 else 0
            if ratio < self.config["ratio_minimo_rb"] - 0.1:
                errores.append(f"Ratio R/B {round(ratio,2)}x menor al minimo {self.config['ratio_minimo_rb']}x")

        # Verifica confluencia
        if señal.get("confluencia") not in ["ALTA"]:
            warnings.append(f"Confluencia {señal.get('confluencia')} — preferible ALTA")

        # Verifica horario
        horario = self.verificar_horario_optimo()
        if not horario["horario_optimo"]:
            warnings.append(horario["mensaje"])

        # Verifica limites globales
        limites = self.verificar_limites()
        if not limites["permitido"]:
            errores.append(limites["razon"])

        # Calcula tamaño de posicion
        tamaño = self.calcular_tamaño_posicion(precio, sl) if precio and sl else {}

        aprobada = len(errores) == 0

        return {
            "aprobada":   aprobada,
            "errores":    errores,
            "warnings":   warnings,
            "tamaño":     tamaño,
            "horario":    horario,
        }

    def registrar_apertura(self, simbolo: str, precio: float, cantidad: float, sl: float, tp1: float, tp2: float, accion: str):
        operacion = {
            "simbolo":   simbolo,
            "accion":    accion,
            "precio":    precio,
            "cantidad":  cantidad,
            "sl":        sl,
            "tp1":       tp1,
            "tp2":       tp2,
            "apertura":  datetime.now().strftime("%H:%M:%S"),
        }
        self.operaciones_abiertas.append(operacion)
        self.operaciones_hoy.append(operacion)
        print(f"[gestion_riesgo] Operacion registrada: {accion} {simbolo} @ {precio} | cantidad={cantidad}")

    def registrar_cierre(self, simbolo: str, precio_cierre: float):
        for op in self.operaciones_abiertas:
            if op["simbolo"] == simbolo:
                if op["accion"] == "COMPRAR":
                    pnl = (precio_cierre - op["precio"]) * op["cantidad"]
                else:
                    pnl = (op["precio"] - precio_cierre) * op["cantidad"]

                if pnl > 0:
                    self.ganancia_diaria += pnl
                else:
                    self.perdida_diaria  += abs(pnl)

                self.operaciones_abiertas.remove(op)
                print(f"[gestion_riesgo] Cierre {simbolo} @ {precio_cierre} | PnL=${round(pnl,2)}")
                return pnl
        return 0

    def resumen_dia(self) -> dict:
        return {
            "operaciones_abiertas": len(self.operaciones_abiertas),
            "operaciones_hoy":      len(self.operaciones_hoy),
            "ganancia_diaria_usd":  round(self.ganancia_diaria, 2),
            "perdida_diaria_usd":   round(self.perdida_diaria, 2),
            "pnl_neto":             round(self.ganancia_diaria - self.perdida_diaria, 2),
            "capital_en_riesgo":    f"{self.config['riesgo_por_operacion']*100}% por operacion",
        }

# Instancia global compartida entre agentes
gestor = GestorRiesgo()