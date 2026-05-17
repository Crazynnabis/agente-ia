# agente_financiero/utils.py
import time
import functools
import asyncio
from datetime import datetime

def con_reintento(max_intentos: int = 3, espera: float = 2.0, valor_default=None):
    def decorador(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for intento in range(1, max_intentos + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if intento == max_intentos:
                        print(f"[utils] {func.__name__} falló {max_intentos} veces: {e}")
                        return valor_default
                    print(f"[utils] {func.__name__} intento {intento} falló: {e} — reintentando en {espera}s...")
                    time.sleep(espera)
        return wrapper
    return decorador

def con_reintento_async(max_intentos: int = 3, espera: float = 2.0, valor_default=None):
    def decorador(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for intento in range(1, max_intentos + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if intento == max_intentos:
                        print(f"[utils] {func.__name__} falló {max_intentos} veces: {e}")
                        return valor_default
                    print(f"[utils] {func.__name__} intento {intento} falló: {e} — reintentando en {espera}s...")
                    await asyncio.sleep(espera)
        return wrapper
    return decorador

def con_timeout(segundos: int = 30, valor_default=None):
    def decorador(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import signal
            def handler(signum, frame):
                raise TimeoutError(f"{func.__name__} excedió {segundos}s")
            try:
                signal.signal(signal.SIGALRM, handler)
                signal.alarm(segundos)
                resultado = func(*args, **kwargs)
                signal.alarm(0)
                return resultado
            except TimeoutError as e:
                print(f"[utils] Timeout: {e}")
                return valor_default
            except AttributeError:
                # Windows no soporta SIGALRM — ejecuta sin timeout
                return func(*args, **kwargs)
        return wrapper
    return decorador

def medir_tiempo(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        inicio = time.time()
        resultado = func(*args, **kwargs)
        duracion = round(time.time() - inicio, 2)
        print(f"[utils] {func.__name__} completado en {duracion}s")
        return resultado
    return wrapper

def medir_tiempo_async(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        inicio = time.time()
        resultado = await func(*args, **kwargs)
        duracion = round(time.time() - inicio, 2)
        print(f"[utils] {func.__name__} completado en {duracion}s")
        return resultado
    return wrapper

class CircuitBreaker:
    def __init__(self, nombre: str, max_fallos: int = 5, tiempo_reset: int = 60):
        self.nombre       = nombre
        self.max_fallos   = max_fallos
        self.tiempo_reset = tiempo_reset
        self.fallos       = 0
        self.ultimo_fallo = None
        self.abierto      = False

    def registrar_fallo(self):
        self.fallos += 1
        self.ultimo_fallo = time.time()
        if self.fallos >= self.max_fallos:
            self.abierto = True
            print(f"[circuit_breaker] {self.nombre} ABIERTO — demasiados fallos")

    def registrar_exito(self):
        self.fallos = 0
        self.abierto = False

    def puede_ejecutar(self) -> bool:
        if not self.abierto:
            return True
        if self.ultimo_fallo and (time.time() - self.ultimo_fallo) > self.tiempo_reset:
            self.abierto = False
            self.fallos  = 0
            print(f"[circuit_breaker] {self.nombre} CERRADO — reiniciando")
            return True
        return False

# Circuit breakers para APIs externas
cb_binance  = CircuitBreaker("Binance",  max_fallos=5, tiempo_reset=60)
cb_newsapi  = CircuitBreaker("NewsAPI",  max_fallos=3, tiempo_reset=120)
cb_firecrawl = CircuitBreaker("Firecrawl", max_fallos=3, tiempo_reset=120)
cb_ollama   = CircuitBreaker("Ollama",   max_fallos=3, tiempo_reset=30)
cb_coingecko = CircuitBreaker("CoinGecko", max_fallos=3, tiempo_reset=60)