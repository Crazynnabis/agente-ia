import re

fixes = {
    "agente_financiero/agente_petroleo.py": "agente_petroleo",
    "agente_financiero/agente_youtube.py":  "agente_youtube",
}

for archivo, nombre_agente in fixes.items():
    try:
        with open(archivo, "r", encoding="utf-8") as f:
            contenido = f.read()
        original = contenido

        # Agrega agente= si no existe
        contenido = re.sub(
            r'(await chat\([^)]*?max_tokens=\d+)\s*\)',
            f'\\1,\n        agente="{nombre_agente}"\n    )',
            contenido
        )

        if contenido != original:
            with open(archivo, "w", encoding="utf-8") as f:
                f.write(contenido)
            print(f"OK: {archivo}")
        else:
            print(f"Sin cambios: {archivo} — revisar manualmente")
    except Exception as e:
        print(f"Error {archivo}: {e}")