"""Analítica: rendimiento por deporte, mercado, unidad, rango de cuota y mes."""

from __future__ import annotations

import streamlit as st

from core.analytics import breakdown, monthly_summary, summarize_bets
from ui import charts
from ui import components as ui
from ui.state import load

_DIMENSIONS = {"sport": "Deporte", "market": "Mercado", "unit_type": "Unidad", "odds_band": "Rango de cuota"}


def render() -> None:
    bets, cfg = load()
    m = summarize_bets(bets, cfg)
    c = cfg.currency
    ui.page_header("Analítica financiera", "Dónde se gana y dónde se pierde dinero.", "insights")

    ui.stat_cards([
        {"label": "Beneficio neto", "value": ui.money(m["net_profit"], c, signed=True), "icon": "savings", "tone": ui.tone_for(m["net_profit"])},
        {"label": "ROI del bank", "value": ui.pct(m["roi_bank"], signed=True), "icon": "account_balance", "tone": ui.tone_for(m["roi_bank"]),
         "help": "Neto / bank inicial"},
        {"label": "Yield", "value": ui.pct(m["yield"], signed=True), "icon": "percent", "tone": ui.tone_for(m["yield"]),
         "help": "Neto / total apostado"},
        {"label": "Mejor racha", "value": f"{m['streaks']['best_win']} G", "icon": "local_fire_department", "tone": "success",
         "help": f"Peor: {m['streaks']['best_loss']} P seguidas"},
        {"label": "Kelly medio", "value": f"{m['kelly_reference'] * 100:.1f}%", "icon": "functions", "tone": "info",
         "help": "Según confianza declarada"},
    ])

    if not m["settled_bets"]:
        ui.empty_state("Sin apuestas liquidadas", "La analítica aparece cuando liquidas al menos una apuesta.", "query_stats")
        return
    if m["settled_bets"] < 30:
        st.info(f"Muestra de {m['settled_bets']} apuestas: los porcentajes aún varían mucho. "
                "Las conclusiones son más fiables a partir de 30–50.", icon=":material/info:")

    tabs = st.tabs([f":material/{icon}: {label}" for icon, label in
                    (("sports", "Deporte"), ("storefront", "Mercado"), ("stairs", "Unidad"), ("tune", "Rango de cuota"), ("calendar_month", "Mensual"))])
    for tab, (key, label) in zip(tabs, _DIMENSIONS.items()):
        with tab:
            data = breakdown(bets, key)
            left, right = st.columns([1.2, 1], gap="medium")
            left.plotly_chart(charts.profit_bars(data, key, f"Beneficio neto por {label.lower()}"),
                              width="stretch", config={"displayModeBar": False}, key=f"bd_chart_{key}")
            right.dataframe(
                data.rename(columns={key: label}), width="stretch", hide_index=True,
                column_config={
                    "apostado": st.column_config.NumberColumn("Apostado", format="$%,.0f"),
                    "neto": st.column_config.NumberColumn("Neto", format="$%,.0f"),
                    "yield": st.column_config.ProgressColumn("Yield %", format="%.1f%%", min_value=-100, max_value=100),
                    "win_rate": st.column_config.NumberColumn("Win %", format="%.1f%%"),
                    "apuestas": "Apuestas",
                },
            )
    with tabs[-1]:
        monthly = monthly_summary(bets)
        st.plotly_chart(charts.monthly_bars(monthly), width="stretch", config={"displayModeBar": False})
