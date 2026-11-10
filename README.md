# Rushbet BankMaster Pro

Gestión profesional de capital para apuestas deportivas con Python, Streamlit, Plotly, Pandas y SQLite.

## Qué hace

- **Dashboard ejecutivo**: bank actual, variación, progreso a la meta de breakeven, yield, win rate, drawdown,
  exposición abierta, CLV, curva del bank con zona de drawdown, donut de resultados y últimos movimientos.
- **Nueva apuesta con asesor de riesgo en vivo**: probabilidad implícita vs. tu estimación, valor esperado,
  Kelly completo y fraccional, unidad sugerida por confianza y alertas del plan (riesgo por apuesta,
  stake especial, exposición abierta, apuestas sin ventaja). Bloquea stakes por encima del máximo especial.
- **Historial**: liquidación en un clic (ganada / perdida / nula), filtros y búsqueda, edición completa,
  borrado con confirmación, exportación e importación CSV.
- **Analítica**: rendimiento por deporte, mercado, unidad, rango de cuota y mes.
- **AI Analyst**: informe con Gemini (plantillas de preguntas) o diagnóstico local si no hay clave.
- **Configuración**: bank, suscripción, meta, límites de riesgo, fracción de Kelly y staking fijo o dinámico.
- Tema claro / oscuro automático, diseño adaptable a celular y movimiento reducido.

## Estructura

```text
app.py                  # entrada: navegación, logo, tarjeta del bank en la barra lateral
core/                   # lógica sin Streamlit (probada con pytest)
  models.py             #   estados, BankSettings, cálculo del neto
  database.py           #   SQLite, validación, migración v1, CSV
  analytics.py          #   métricas, desgloses, plan de unidades, asesor de stake
  ai_analyst.py         #   Gemini + informe local
ui/
  components.py         # piezas visuales (hero, indicadores, semáforo, línea de tiempo…)
  charts.py             # gráficos Plotly con la identidad de la app
  views/                # una página por archivo
assets/                 # style.css (sistema de diseño), logo e icono
.streamlit/config.toml  # tema nativo claro/oscuro
tests/                  # pruebas de núcleo y de humo de cada página
```

## Instalación y ejecución

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
streamlit run app.py
```

Pruebas: `pip install pytest && pytest -q`

## Variables de entorno / Secrets

| Variable | Uso |
|---|---|
| `GEMINI_API_KEY` | Activa Gemini (en `.env`, variable de entorno o Secrets de Streamlit Cloud). |
| `GEMINI_MODEL` | Modelo a usar (por defecto `gemini-2.5-flash`). |
| `RBM_DB_PATH` | Ruta del archivo SQLite (por defecto `rushbet_bankmaster.db` junto a la app). |

> En Streamlit Community Cloud el disco se borra al reiniciar la app. Descarga el CSV desde
> **Historial → Respaldo** con frecuencia y vuelve a importarlo si hace falta.

## Plan financiero por defecto

| Unidad | Confianza mínima | % del bank | Stake (bank 250.000) |
|---|---|---|---|
| 1U Base | 70% | 2% | $5.000 |
| 2U Moderado | 75% | 4% | $10.000 |
| 3U Alto | 85% | 6% | $15.000 |
| 4U Máximo | 90% | 10% | $25.000 |
| Whale | 95% | 10% (tope $150.000) | $25.000 |

Bank inicial $250.000 COP · suscripción $120.000 · meta breakeven neta $370.000.

## Definiciones

- **Yield** = beneficio neto / total apostado. **ROI del bank** = beneficio neto / bank inicial.
- **Win rate** = ganadas / (ganadas + perdidas); las nulas no cuentan.
- **Kelly** = (p·b − q) / b con b = cuota − 1; se recomienda ¼ Kelly.
- **CLV** = cuota tomada / cuota de cierre − 1.

## Migración desde v1

Al iniciar, las apuestas guardadas con el par antiguo `status`/`result` se unifican en un solo estado y se
recalcula su neto (v1 permitía, por ejemplo, estado «open» con resultado «won» y neto 0).

## Aviso

Herramienta educativa de gestión de bankroll. No garantiza resultados ni sustituye asesoría profesional.
Apuesta con responsabilidad.
