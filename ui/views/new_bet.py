"""Registro rápido: partido, selección, cuota y recomendación; el programa ajusta el stake."""

from __future__ import annotations

from datetime import date

import streamlit as st

from core import database as db
from core.analytics import (RECOMMENDATION_MODES, STAKE_RULES, advise_stake, available_bankroll,
                            plan_recommendation, staking_base)
from core.models import DEFAULT_MARKETS, SPORT_MARKETS, SPORTS, STATUSES
from ui import components as ui
from ui.state import load

_FIELDS = (
    "qb_sport", "qb_event", "qb_selection", "qb_odds", "qb_rec_mode", "qb_confidence",
    "qb_percentage", "qb_amount", "qb_manual", "qb_manual_stake", "qb_market",
    "qb_market_custom", "qb_date", "qb_status", "qb_closing", "qb_notes",
)
SPORT_HINTS = {
    "Fútbol": "Millonarios vs Nacional",
    "Baloncesto": "Lakers vs Warriors",
    "Tenis": "Alcaraz vs Sinner",
}
SELECTION_HINTS = {
    "Fútbol": "Local, empate, ambos marcan, más de 2.5…",
    "Baloncesto": "Local, visitante, -5.5, más de 215.5…",
    "Tenis": "Jugador 1, jugador 2, más de 22.5 juegos…",
}


def _reset() -> None:
    for key in _FIELDS:
        st.session_state.pop(key, None)


def _sport_changed() -> None:
    for key in ("qb_market", "qb_market_custom"):
        st.session_state.pop(key, None)


def _market(sport: str) -> str:
    options = SPORT_MARKETS.get(sport, DEFAULT_MARKETS) + ("Otro mercado…",)
    choice = st.selectbox("Mercado", options, key="qb_market")
    if choice == "Otro mercado…":
        return st.text_input("Nombre del mercado", key="qb_market_custom").strip()
    return choice


def _recommendation_input(base: float, cfg) -> tuple[str, float]:
    mode = st.segmented_control(
        "¿Cómo recibiste la recomendación?",
        list(RECOMMENDATION_MODES),
        default="confidence",
        format_func=RECOMMENDATION_MODES.get,
        key="qb_rec_mode",
        width="stretch",
    ) or "confidence"
    if mode == "confidence":
        value = st.segmented_control(
            "Nivel de confianza",
            [70, 75, 80, 85, 90],
            default=80,
            format_func=lambda number: f"{number}%",
            key="qb_confidence",
            width="stretch",
            help="70→5% · 75→10% · 80→20% · 85→25% · 90→30% del bank",
        )
    elif mode == "percentage":
        value = st.segmented_control(
            "Porcentaje indicado",
            [5, 10, 20, 25, 30],
            default=20,
            format_func=lambda number: f"{number}%",
            key="qb_percentage",
            width="stretch",
        )
    else:
        suggested = min(base * 0.20, cfg.max_special_stake)
        value = st.number_input(
            f"Monto recomendado ({cfg.currency})",
            min_value=1.0,
            value=float(suggested),
            step=1000.0,
            format="%.2f",
            key="qb_amount",
        )
    return mode, float(value)


def render() -> None:
    bets, cfg = load()
    currency = cfg.currency
    total_bank = cfg.base_bankroll + sum(float(bet.get("net_profit") or 0) for bet in bets)
    available = available_bankroll(bets, cfg)
    base = staking_base(bets, cfg)

    ui.show_flash()
    ui.page_header(
        "Digitalizar apuesta",
        "Escribe el partido, la selección, la cuota y la recomendación. El programa calcula el resto.",
        "add_circle",
        badges=[{"text": "Registro rápido", "tone": "success", "icon": "bolt"}],
    )
    ui.stat_cards([
        {"label": "Bank total", "value": ui.money(total_bank, currency), "icon": "account_balance", "tone": "info"},
        {"label": "Reserva protegida", "value": ui.money(cfg.protected_reserve, currency), "icon": "lock", "tone": "neutral"},
        {"label": "Disponible para apostar", "value": ui.money(available, currency), "icon": "payments", "tone": "success"},
        {"label": "Base del cálculo", "value": ui.money(base, currency), "icon": "percent", "tone": "info",
         "help": f"Modo {cfg.staking_mode}"},
    ])

    entry_col, plan_col = st.columns([1.25, 1], gap="large")
    with entry_col:
        with st.container(border=True):
            ui.section_title("Apuesta", "sports_soccer", "Solo los datos indispensables.")
            sport = st.selectbox("Deporte", SPORTS, key="qb_sport", on_change=_sport_changed)
            event = st.text_input("Partido", placeholder=SPORT_HINTS.get(sport, "Participante A vs Participante B"), key="qb_event")
            selection = st.text_input("Selección o pronóstico", placeholder=SELECTION_HINTS.get(sport, "Escribe la selección"), key="qb_selection")
            odds = st.number_input("Cuota decimal", min_value=1.01, value=2.00, step=0.01, format="%.2f", key="qb_odds")

            ui.section_title("Recomendación", "recommend", "Acepta nivel, porcentaje o monto del tipster.")
            recommendation_mode, recommendation_value = _recommendation_input(base, cfg)
            plan = plan_recommendation(recommendation_mode, recommendation_value, base, cfg)

            manual = st.toggle("Ajustar manualmente el stake final", value=False, key="qb_manual")
            if manual:
                stake = st.number_input(
                    f"Stake final ({currency})", min_value=1.0, value=float(plan.final_stake or 1),
                    step=1000.0, format="%.2f", key="qb_manual_stake",
                )
            else:
                stake = plan.final_stake

            with st.expander("Más detalles (opcionales)", icon=":material/tune:"):
                market = _market(sport)
                a, b = st.columns(2)
                bet_date = a.date_input("Fecha", value=date.today(), key="qb_date", format="YYYY-MM-DD")
                status = b.selectbox("Estado", list(STATUSES), format_func=STATUSES.get, key="qb_status")
                closing = a.number_input("Cuota de cierre", min_value=0.0, value=0.0, step=0.01,
                                         format="%.2f", key="qb_closing")
                notes = st.text_area("Notas", placeholder="Tipster, razonamiento, fuente…", key="qb_notes", height=75)

    advice = advise_stake(odds, plan.confidence, stake, bets, cfg, selected_unit=plan.unit)
    adjustments = list(plan.adjustments)
    if manual and abs(stake - plan.final_stake) > 0.01:
        adjustments.append({"tone": "info", "text": f"Ajuste manual: {ui.money(plan.final_stake, currency)} → {ui.money(stake, currency)}."})
    alerts = adjustments + advice.alerts

    missing = not event.strip() or not selection.strip() or not market.strip()
    blocked = missing or stake <= 0 or stake > available or stake > cfg.max_special_stake
    status_text = None
    if missing:
        level, status_text = "warning", "Completa partido y selección"
    elif blocked:
        level = "danger"
    elif any(item["tone"] in ("warning", "danger") for item in alerts):
        level = "warning"
    else:
        level = "success"

    with plan_col:
        ui.section_title("Tu ticket", "confirmation_number")
        ui.bet_slip(
            stake=stake, payout=stake * odds, profit=stake * (odds - 1), unit=plan.unit,
            pct_bank=round(plan.percentage, 2), odds=odds, currency=currency, level=level,
            alerts=alerts, event=event.strip(), selection=selection.strip(), status_text=status_text,
        )
        if st.button("Guardar apuesta", type="primary", icon=":material/save:", width="stretch", disabled=blocked):
            reasons = "; ".join(item["text"] for item in adjustments)
            try:
                bet_id = db.add_bet(
                    bet_date=bet_date.isoformat(), sport=sport, market=market, event_name=event,
                    selection=selection, odds=odds, stake=stake, confidence=plan.confidence,
                    unit_type=plan.unit, status=status, closing_odds=closing or None, notes=notes,
                    recommendation_type=recommendation_mode, recommended_value=recommendation_value,
                    recommended_stake=plan.recommended_stake, adjustment_reason=reasons,
                )
            except ValueError as exc:
                st.error(str(exc), icon=":material/error:")
            else:
                _reset()
                ui.flash(f"Apuesta #{bet_id} guardada: {plan.unit}, stake {ui.money(stake, currency)}.")
                st.rerun()
        if missing:
            pass  # el propio ticket ya lo indica
        elif stake <= 0:
            st.caption("Con esta recomendación el plan dice no apostar.")
        elif stake > available:
            st.caption("El monto supera el bank disponible después de la reserva.")
        elif stake > cfg.max_special_stake:
            st.caption(f"El monto supera el tope de {ui.money(cfg.max_special_stake, currency)}.")

        with st.expander("Ver cálculo", icon=":material/calculate:"):
            if plan.recommended_stake and abs(plan.recommended_stake - stake) > 0.01:
                st.write(f"Recomendado por el plan: **{ui.money(plan.recommended_stake, currency)}** → "
                         f"apuesta final **{ui.money(stake, currency)}**.")
            for note in (item for item in alerts if item["tone"] == "info"):
                st.caption(note["text"])
            c1, c2 = st.columns(2)
            c1.metric("Prob. de la cuota", f"{advice.implied_prob:.1f}%")
            c2.metric("Tu confianza", f"{advice.estimated_prob:.0f}%")
            c1.metric("Ventaja", f"{advice.edge:+.1f} pp")
            c2.metric("Valor esperado", ui.money(advice.expected_value, currency, signed=True))
