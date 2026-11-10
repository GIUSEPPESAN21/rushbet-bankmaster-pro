# Rushbet BankMaster Pro

Gestión profesional de capital para apuestas deportivas con Python, Streamlit, Plotly, Pandas y SQLite.

## Qué hace

- **Dashboard ejecutivo**: bank actual, variación, progreso a la meta de breakeven, yield, win rate, drawdown,
  exposición abierta, CLV, curva del bank con zona de drawdown, donut de resultados y últimos movimientos.
- **Nueva apuesta guiada y automatizada**: primero eliges fútbol, baloncesto o tenis y la app muestra sus mercados frecuentes;
  el porcentaje de confianza recomendado asigna automáticamente el stake acordado (70%→5%, 75%→10%,
  80%→20%, 85%→25%, 90%→30% del bank). También muestra
  probabilidad implícita, valor esperado, Kelly y alertas del plan. El modo manual permanece disponible para casos especiales.
- **Historial**: liquidación en un clic (ganada / perdida / nula), filtros y búsqueda, edición completa,
  borrado con confirmación, exportación/importación CSV y registro de auditoría de cada cambio.
- **Analítica**: rendimiento por deporte, mercado, unidad, rango de cuota y mes.
- **AI Analyst**: informe con Gemini (plantillas de preguntas) o diagnóstico local si no hay clave.
- **Configuración**: bank, suscripción, meta, límites de riesgo, fracción de Kelly y staking fijo o dinámico.
- Tema claro / oscuro automático, diseño adaptable a celular y movimiento reducido.

## Estructura

```text
app.py                  # entrada: navegación, logo, tarjeta del bank en la barra lateral
core/                   # lógica sin Streamlit (probada con pytest)
  models.py             #   estados, BankSettings, cálculo del neto
  database.py           #   SQLite/PostgreSQL, transacciones, auditoría, migración v1, CSV
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
| `DATABASE_URL` | URL PostgreSQL persistente para producción. Es obligatoria para conservar datos tras reinicios en Streamlit Cloud. |
| `RBM_DB_PATH` | Ruta SQLite local; tiene prioridad en pruebas y desarrollo. |

> En Streamlit Community Cloud configura `DATABASE_URL` con una conexión PostgreSQL; su disco local se borra al
> reiniciar. Sin esa variable la app continúa con SQLite y muestra una advertencia. La exportación CSV de
> **Historial → Respaldo** sigue disponible como copia adicional.

## Plan financiero por defecto

| Unidad | Confianza recomendada | % exacto del bank | Stake (bank 250.000) |
|---|---|---|---|
| 1U Base | 70–74% | 5% | $12.500 |
| 2U Moderado | 75–79% | 10% | $25.000 |
| 3U Alto | 80–84% | 20% | $50.000 |
| 4U Máximo | 85–89% | 25% | $62.500 |
| Whale | 90–100% | 30% (tope $150.000) | $75.000 |

Con menos de 70% el modo automático recomienda no apostar. El cálculo usa el bank inicial en modo fijo y el bank
actual en modo dinámico; conserva centavos cuando el porcentaje exacto no produce un número entero.

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
