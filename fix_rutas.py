import os

archivos = [
    'loop_automatico.py',
    'loop_rapido.py',
    'agente_financiero/agente_macro.py',
    'agente_financiero/agente_petroleo.py',
    'agente_financiero/agente_sentimiento.py',
    'agente_financiero/alertas_telegram.py',
    'agente_financiero/ejecutor_alpaca.py',
    'agente_financiero/logger_trading.py',
    'agente_financiero/telegram_comandos.py',
    'nucleo/cliente_ia.py',
]

for archivo in archivos:
    try:
        with open(archivo, 'r', encoding='utf-8') as f:
            contenido = f.read()
        original = contenido

        # Elimina rutas hardcodeadas
        contenido = contenido.replace(
            "os.environ[\"DOTENV_PATH\"] = r'C:\\Users\\Oscar Hernandez\\.env'", "")
        contenido = contenido.replace(
            "os.environ['DOTENV_PATH'] = r'C:\\Users\\Oscar Hernandez\\.env'", "")
        contenido = contenido.replace(
            "load_dotenv(r'C:\\Users\\Oscar Hernandez\\.env', override=True)",
            "load_dotenv(override=True)")
        contenido = contenido.replace(
            "sys.path.insert(0, r'C:\\Users\\Oscar Hernandez\\agente-ia')", "")
        contenido = contenido.replace(
            "r'C:\\Users\\Oscar Hernandez\\agente-ia\\logs'",
            "os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')")

        if contenido != original:
            with open(archivo, 'w', encoding='utf-8') as f:
                f.write(contenido)
            print(f'OK: {archivo}')
        else:
            print(f'Sin cambios: {archivo}')
    except Exception as e:
        print(f'Error {archivo}: {e}')

print('Listo.')