"""Nueva apuesta con asesor de riesgo en vivo (ventaja, Kelly fraccional y reglas del plan)."""

from __future__ import annotations

from datetime import date

import streamlit as st

from core import database as db
from core.analytics import advise_stake, get_stake_profile, staking_base, unit_for_confidence
from core.models import SPORTS, STATUSES, UNIT_TYPES
from ui import charts
from ui import components as ui
from ui.state import load

_FIELDS = ("nb_sport", "nb_market", "nb_event", "nb_selection", "nb_odds", "nb_stake", "nb_conf", "nb_unit",
           "nb_status", "nb_closing", "nb_notes", "nb_date", "nb_follow")


def _reset() -> None:
    for key in _FIELDS:
        st.session_state.pop(key, None)


def render() -> None:
    bets, cfg = load()
    c = cfg.currency
    ui.show_flash()
    ui.page_header("Nueva apuesta", "Registra la jugada y valida el riesgo antes de guardarla.", "add_circle")

    form_col, advice_col = st.columns([1.35, 1], gap="large")
    with form_col:
        with st.container(border=True):
            ui.section_title("Datos del evento", "sports_soccer")
            a, b = st.columns(2)
            a.date_input("Fecha", value=date.today(), key="nb_date", format="YYYY-MM-DD")
            b.selectbox("Deporte", SPORTS, key="nb_sport")
            st.text_input("Evento", placeholder="Equipo A vs Equipo B", key="nb_event")
            a, b = st.columns(2)
            a.text_input("Mercado", value="1X2", key="nb_market")
            b.text_input("Selección", placeholder="Local, Over 2.5, …", key="nb_selection")

            ui.section_title("Precio y stake", "payments")
            a, b, d = st.columns(3)
            odds = a.number_input("Cuota decimal", min_value=1.01, value=2.00, step=0.05, format="%.2f", key="nb_odds")
            confidence = b.slider("Confianza (%)", 50, 99, 80, key="nb_conf",
                                  help="Tu probabilidad estimada de acierto. Se compara con la probabilidad implícita de la cuota.")
            base = staking_base(bets, cfg)
            suggested_unit = unit_for_confidence(confidence)
            profile = {row["unit"]: row["cash"] for row in get_stake_profile(base, cfg)}
            d.selectbox("Unidad", UNIT_TYPES, index=UNIT_TYPES.index(suggested_unit) if suggested_unit in UNIT_TYPES else 0,
                        key="nb_unit", help=f"Sugerida por confianza: {suggested_unit}")
            follow = st.toggle("Usar el stake de la unidad elegida", value=True, key="nb_follow")
            unit_cash = profile.get(st.session_state.get("nb_unit", "1U"), profile["1U"])
            if follow:
                stake = float(unit_cash)
                st.caption(f"Stake según plan: **{ui.money(stake, c)}**")
            else:
                stake = st.number_input(f"Stake ({c})", min_value=1000.0, value=float(unit_cash), step=1000.0, format="%.0f")

            a, b = st.columns(2)
            status = a.selectbox("Estado", list(STATUSES), format_func=STATUSES.get, key="nb_status")
            closing = b.number_input("Cuota de cierre (opcional)", min_value=0.0, value=0.0, step=0.05, format="%.2f",
                                     key="nb_closing", help="Para medir el CLV. Déjala en 0 si aún no la conoces.")
            st.text_area("Notas", key="nb_notes", placeholder="Razonamiento, tipster, fuente…", height=80)

    advice = advise_stake(odds, confidence, stake, bets, cfg)
    with advice_col:
        ui.section_title("Asesor de riesgo", "shield", "Se recalcula al cambiar cualquier dato.")
        titles = {"success": "Dentro del plan", "warning": "Revisa antes de entrar", "danger": "Riesgo alto: no recomendada"}
        ui.risk_card(advice.level, titles[advice.level], [
            ("Prob. implícita", f"{advice.implied_prob:.1f}%"),
            ("Tu estimación", f"{advice.estimated_prob:.1f}%"),
            ("Valor esperado", ui.money(advice.expected_value, c, signed=True)),
            ("Kelly completo", f"{advice.kelly_full * 100:.1f}%"),
            (f"Kelly ×{cfg.kelly_fraction:g}", ui.money(advice.kelly_stake, c)),
            ("Unidad sugerida", f"{advice.suggested_unit} · {ui.money(advice.unit_stake, c)}"),
        ], advice.alerts)
        st.plotly_chart(charts.kelly_gauge(advice.edge), width="stretch", config={"displayModeBar": False})

        blocked = stake > cfg.max_special_stake
        if st.button("Guardar apuesta", type="primary", icon=":material/save:", width="stretch", disabled=blocked):
            try:
                bet_id = db.add_bet(
                    bet_date=st.session_state["nb_date"].isoformat(), sport=st.session_state["nb_sport"],
                    market=st.session_state["nb_market"], event_name=st.session_state["nb_event"],
                    selection=st.session_state["nb_selection"], odds=odds, stake=stake, confidence=confidence,
                    unit_type=st.session_state["nb_unit"], status=status, closing_odds=closing or None,
                    notes=st.session_state["nb_notes"],
                )
            except ValueError as exc:
                st.error(str(exc), icon=":material/error:")
            else:
                _reset()
                ui.flash(f"Apuesta #{bet_id} guardada.")
                st.rerun()
        if blocked:
            st.caption(f"Bloqueado: el stake supera el máximo especial de {ui.money(cfg.max_special_stake, c)}.")
