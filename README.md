# Rushbet BankMaster Pro

Aplicación profesional de gestión de capital para apuestas deportivas con Python, Streamlit, Plotly, Pandas y SQLite.

## Objetivo

Rushbet BankMaster Pro permite:

- registrar apuestas con stake, confianza, mercado y rendimiento real,
- controlar el bankroll operativo de forma disciplinada,
- medir ROI, Yield, Win Rate y Kelly reference,
- gestionar la meta de breakeven neta del grupo tipster,
- analizar el plan de staking con alertas de riesgo,
- generar recomendaciones de estrategia con Gemini 3 Flash si la API está configurada.

## Estructura del proyecto

```text
rushbet-bankmaster/
├── app.py
├── database.py
├── analytics.py
├── ai_analyst.py
├── requirements.txt
├── .gitignore
├── README.md
└── rushbet_bankmaster.db
```

## Requisitos

- Python 3.10+
- Pip o uv

## Instalación

```bash
cd rushbet-bankmaster
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

## Ejecución

```bash
streamlit run app.py
```

## Variables de entorno

Para activar la integración con Gemini 3 Flash, crea un `.env` con:

```bash
GEMINI_API_KEY=tu_api_key_aqui
```

La app no se rompe si la clave no existe; entonces usa un análisis local conservador.

## Regla de planificación financiera

- Bankroll operativo inicial: $250.000 COP
- Suscripción grupo tipster: $120.000 COP
- Breakeven net target: $370.000 COP
- 1U = 2.0% del bankroll = $5.000 COP
- 2U = 4.0% = $10.000 COP
- 3U = 6.0% = $15.000 COP
- 4U = 10.0% = $25.000 COP
- Stake especial: máximo absoluto $150.000 COP con alerta roja si supera el 10% del bankroll.

## Funcionalidades principales

1. Dashboard ejecutivo con KPIs y seguimiento del bankroll.
2. Registro de apuestas con almacenamiento persistente en SQLite.
3. Cálculo de ROI, Yield, Win Rate y Kelly reference.
4. Plan de staking según nivel de confianza.
5. AI Analyst con Gemini 3 Flash (opcional).
6. Configuración centralizada de parámetros del bank y del riesgo.

## Buenas prácticas

- No excedas el 10% del bankroll en apuestas de máximo riesgo.
- Dedica más tiempo a la calidad de selección que al volumen de apuestas.
- Usa la IA únicamente como soporte de análisis, no para reemplazar juicio disciplinado.
- Mantén una base de datos histórica limpia y revisa cada apuesta al cierre del mercado.

## Despliegue sugerido

Puedes desplegar la app en:

- Streamlit Community Cloud
- Railway
- Render
- Docker + servicio web

Ejemplo mínimo de despliegue con Docker:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
```

## Licencia

Proyecto educativo / financiero interno de gestión de bankroll. No sustituye asesoría profesional de inversión o apuestas.
