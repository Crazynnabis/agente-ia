# Agente IA - Sistema de Agentes Inteligentes Autónomos

Este proyecto implementa un sistema multiagente de inteligencia artificial autónoma, donde cada agente opera de forma independiente para resolver tareas especializadas en distintos dominios.

## Descripción

El sistema está compuesto por agentes autónomos que pueden percibir su entorno, tomar decisiones y ejecutar acciones sin intervención humana directa. Cada agente cuenta con su propia lógica de negocio y se comunica con los demás a través del núcleo central.

## Estructura del Proyecto

```
agente-ia/
├── agente_financiero/   # Agente especializado en análisis y gestión financiera
├── agente_contenido/    # Agente especializado en generación y gestión de contenido
├── agente_turistico/    # Agente especializado en recomendaciones y planificación turística
├── nucleo/              # Lógica central: coordinación, comunicación entre agentes y orquestación
├── base_datos/          # Modelos de datos, conexiones y repositorios
└── README.md
```

## Agentes

- **Agente Financiero**: Analiza datos financieros, genera reportes y toma decisiones de inversión o presupuesto de forma autónoma.
- **Agente de Contenido**: Genera, clasifica y gestiona contenido digital adaptado al contexto y audiencia.
- **Agente Turístico**: Planifica rutas, recomienda destinos y gestiona itinerarios de viaje personalizados.

## Núcleo

El módulo `nucleo` actúa como orquestador del sistema: gestiona el ciclo de vida de cada agente, enruta mensajes entre ellos y centraliza la configuración global.

## Base de Datos

El módulo `base_datos` centraliza el acceso a datos persistentes compartidos por todos los agentes.

## Requisitos

- Python 3.10+
- Dependencias definidas en `requirements.txt` (por crear)

## Inicio Rápido

```bash
# Clonar o acceder al proyecto
cd agente-ia

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar el sistema
python -m nucleo
```
