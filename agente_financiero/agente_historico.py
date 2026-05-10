# agente_financiero/agente_historico.py
import yfinance as yf
import pandas as pd
import numpy as np
import ollama
from datetime import datetime, timedelta

ACTIVOS = {
    "acciones": ["AAPL", "NVDA", "MSFT", "TSLA", "SPY", "QQQ"],
    "crypto": ["BTC-USD", "ETH-USD"],
    "materias_primas": ["GC=F", "CL=F"],  # oro, petroleo
}

def obtener_datos_historicos(simbolo: str, años: int = 5) -> pd.DataFrame:
    try:
        fin = datetime.now()
        inicio = fin - timedelta(days=365 * años)
        ticker = yf.Ticker(simbolo)
        df = ticker.history(start=inicio, end=fin)
        return df
    except Exception as e:
        print(f"[agente_historico] Error {simbolo}: {e}")
        return pd.DataFrame()

def calcular_estadisticas(df: pd.DataFrame, simbolo: str) -> dict:
    if df.empty:
        return {"simbolo": simbolo, "error": "Sin datos"}
    
    precios = df["Close"]
    rendimientos = precios.pct_change().dropna()
    
    # Rendimientos por periodo
    rend_1m = ((precios.iloc[-1] / precios.iloc[-22]) - 1) * 100 if len(precios) > 22 else None
    rend_3m = ((precios.iloc[-1] / precios.iloc[-66]) - 1) * 100 if len(precios) > 66 else None
    rend_1a = ((precios.iloc[-1] / precios.iloc[-252]) - 1) * 100 if len(precios) > 252 else None
    rend_total = ((precios.iloc[-1] / precios.iloc[0]) - 1) * 100
    
    # Volatilidad anualizada
    volatilidad = rendimientos.std() * np.sqrt(252) * 100
    
    # Máximo drawdown
    rolling_max = precios.cummax()
    drawdown = ((precios - rolling_max) / rolling_max) * 100
    max_drawdown = drawdown.min()
    
    # Precio actual vs máximo histórico
    precio_actual = precios.iloc[-1]
    precio_max = precios.max()
    distancia_max = ((precio_actual / precio_max) - 1) * 100
    
    # Días en máximo histórico
    en_maximo = precio_actual >= precio_max * 0.98
    
    return {
        "simbolo": simbolo,
        "precio_actual": round(precio_actual, 2),
        "rend_1m": round(rend_1m, 2) if rend_1m else None,
        "rend_3m": round(rend_3m, 2) if rend_3m else None,
        "rend_1a": round(rend_1a, 2) if rend_1a else None,
        "rend_total": round(rend_total, 2),
        "volatilidad_anual": round(volatilidad, 2),
        "max_drawdown": round(max_drawdown, 2),
        "distancia_maximo": round(distancia_max, 2),
        "cerca_maximo_historico": en_maximo,
        "datos_dias": len(df),
    }

def detectar_patrones(df: pd.DataFrame, simbolo: str) -> dict:
    if df.empty or len(df) < 50:
        return {"simbolo": simbolo, "patron": "Sin datos suficientes"}
    
    precios = df["Close"]
    vol = df["Volume"]
    
    # Media movil 50 y 200 dias
    ma50  = precios.rolling(50).mean().iloc[-1]
    ma200 = precios.rolling(200).mean().iloc[-1] if len(precios) >= 200 else None
    precio_actual = precios.iloc[-1]
    
    # Golden cross / Death cross
    patron = "neutral"
    if ma200:
        if ma50 > ma200 and precio_actual > ma50:
            patron = "GOLDEN CROSS — tendencia alcista confirmada"
        elif ma50 < ma200 and precio_actual < ma50:
            patron = "DEATH CROSS — tendencia bajista confirmada"
        elif precio_actual > ma50 > ma200:
            patron = "alcista — precio sobre MA50 y MA200"
        elif precio_actual < ma50 < ma200:
            patron = "bajista — precio bajo MA50 y MA200"
    
    # Volumen anómalo
    vol_promedio = vol.rolling(20).mean().iloc[-1]
    vol_actual = vol.iloc[-1]
    volumen_anomalo = vol_actual > vol_promedio * 1.5
    
    return {
        "simbolo": simbolo,
        "ma50": round(ma50, 2),
        "ma200": round(ma200, 2) if ma200 else None,
        "patron": patron,
        "volumen_anomalo": volumen_anomalo,
    }

def analizar_historico_completo() -> dict:
    todos_stats = []
    todos_patrones = []
    
    todos_simbolos = (
        ACTIVOS["acciones"] +
        ACTIVOS["crypto"] +
        ACTIVOS["materias_primas"]
    )
    
    for simbolo in todos_simbolos:
        print(f"[agente_historico] Analizando {simbolo}...")
        df = obtener_datos_historicos(simbolo, años=3)
        stats = calcular_estadisticas(df, simbolo)
        patron = detectar_patrones(df, simbolo)
        todos_stats.append(stats)
        todos_patrones.append(patron)
    
    # Construye resumen para Ollama
    resumen_stats = "\n".join([
        f"{s['simbolo']}: precio={s.get('precio_actual','N/A')} | "
        f"1m={s.get('rend_1m','N/A')}% | 1a={s.get('rend_1a','N/A')}% | "
        f"vol={s.get('volatilidad_anual','N/A')}% | drawdown={s.get('max_drawdown','N/A')}%"
        for s in todos_stats if "error" not in s
    ])
    
    resumen_patrones = "\n".join([
        f"{p['simbolo']}: {p.get('patron','N/A')} | vol_anomalo={p.get('volumen_anomalo','N/A')}"
        for p in todos_patrones if "error" not in p
    ])
    
    print("[agente_historico] Generando análisis con Ollama...")
    respuesta = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "system",
                "content": """Eres un analista cuantitativo experto en datos históricos de mercados.
Analiza las estadísticas y patrones y entrega:
1. Top 3 activos con mejor perfil riesgo/retorno
2. Activos en tendencia alcista confirmada
3. Activos en tendencia bajista — evitar
4. Oportunidades detectadas (activos lejos de máximos con buen momentum)
5. Riesgos detectados (alta volatilidad, drawdowns extremos)
6. Recomendación de asignación de portafolio (% sugerido por categoría)
Responde en español, conciso y accionable."""
            },
            {
                "role": "user",
                "content": f"ESTADÍSTICAS HISTÓRICAS:\n{resumen_stats}\n\nPATRONES TÉCNICOS:\n{resumen_patrones}"
            }
        ]
    )
    
    return {
        "estadisticas": todos_stats,
        "patrones": todos_patrones,
        "analisis": respuesta["message"]["content"],
        "modelo": "llama3.2"
    }

def obtener_reporte_historico() -> str:
    resultado = analizar_historico_completo()
    return resultado.get("analisis", "Sin análisis histórico disponible")