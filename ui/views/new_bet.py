"""Nueva apuesta con captura guiada y stake automático por confianza.

Flujo principal: deporte → mercado → recomendación (%) → unidad → porcentaje exacto del bank.
El modo manual sigue disponible para no quitar comportamiento existente.
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from core import database as db
from core.analytics import (STAKE_RULES, advise_stake, get_stake_profile, staking_base,
                            unit_for_confidence)
from core.models import DEFAULT_MARKETS, SPORT_MARKETS, SPORTS, STATUSES, UNIT_TYPES
from ui import charts
from ui import components as ui
from ui.state import load

_FIELDS = (
    "nb_sport", "nb_market_choice", "nb_market_custom", "nb_event", "nb_selection",
    "nb_odds", "nb_conf", "nb_auto_stake", "nb_unit", "nb_exact_unit", "nb_manual_stake",
    "nb_status", "nb_closing", "nb_notes", "nb_date",
)

SPORT_HINTS = {
    "Fútbol": "Ej.: Millonarios vs Nacional",
    "Baloncesto": "Ej.: Lakers vs Warriors",
    "Tenis": "Ej.: Alcaraz vs Sinner",
}
SELECTION_HINTS = {
    "1X2": "Local, Empate o Visitante",
    "Doble oportunidad": "Local o empate, Local o visitante…",
    "Total de goles": "Más de 2.5, Menos de 3.5…",
    "Ambos marcan": "Sí o No",
    "Hándicap asiático": "Local -0.5, Visitante +1.0…",
    "Córners": "Más de 9.5 córners…",
    "Tarjetas": "Más de 4.5 tarjetas…",
    "Ganador": "Local o Visitante",
    "Hándicap": "Local -5.5, Visitante +3.5…",
    "Total de puntos": "Más de 215.5, Menos de 220.5…",
    "Total del equipo": "Local más de 108.5…",
    "Ganador del partido": "Jugador 1 o Jugador 2",
    "Hándicap de juegos": "Jugador 1 -2.5 juegos…",
    "Total de juegos": "Más de 22.5 juegos…",
    "Ganador del set": "Jugador 1 o Jugador 2",
}


def _reset() -> None:
    for key in _FIELDS:
        st.session_state.pop(key, None)


def _sport_changed() -> None:
    """Un cambio de deporte invalida el mercado anterior, no los demás datos."""
    for key in ("nb_market_choice", "nb_market_custom", "nb_selection"):
        st.session_state.pop(key, None)


def _market_changed() -> None:
    st.session_state.pop("nb_selection", None)


def _market_input(sport: str) -> str:
    markets = SPORT_MARKETS.get(sport, DEFAULT_MARKETS) + ("Otro mercado…",)
    choice = st.selectbox(
        "Mercado",
        markets,
        key="nb_market_choice",
        on_change=_market_changed,
        help="Se muestran primero los mercados más usados para el deporte elegido.",
    )
    if choice == "Otro mercado…":
        return st.text_input("Nombre del mercado", key="nb_market_custom", placeholder="Escribe el mercado").strip()
    return choice


def _plan_percent(unit: str, cfg) -> float:
    return float(STAKE_RULES.get(unit, {}).get("pct", 0.0))


def render() -> None:
    bets, cfg = load()
    currency = cfg.currency
    ui.show_flash()
    ui.page_header(
        "Nueva apuesta",
        "El porcentaje recomendado calcula automáticamente la unidad y el stake exacto.",
        "add_circle",
        badges=[{"text": "70%→5% · 75%→10% · 80%→20% · 85%→25% · 90%→30%", "tone": "info", "icon": "percent"}],
    )

    form_col, advice_col = st.columns([1.35, 1], gap="large")
    with form_col:
        with st.container(border=True):
            ui.section_title("1. Deporte y mercado", "sports_soccer", "Fútbol, baloncesto y tenis tienen mercados rápidos.")
            a, b = st.columns([0.8, 1.2])
            a.date_input("Fecha", value=date.today(), key="nb_date", format="YYYY-MM-DD")
            sport = b.selectbox("Deporte", SPORTS, key="nb_sport", on_change=_sport_changed)
            event = st.text_input("Evento", placeholder=SPORT_HINTS.get(sport, "Equipo o participante A vs B"), key="nb_event")
            market = _market_input(sport)
            selection = st.text_input(
                "Selección",
                placeholder=SELECTION_HINTS.get(market, "Escribe la selección recomendada"),
                key="nb_selection",
                help="Incluye la línea completa cuando aplique: por ejemplo, Más de 2.5.",
            )

            ui.section_title("2. Recomendación y porcentaje", "percent",
                             "La confianza decide la unidad. Puedes usar el modo manual cuando sea necesario.")
            a, b = st.columns(2)
            odds = a.number_input("Cuota decimal", min_value=1.01, value=2.00, step=0.01, format="%.2f", key="nb_odds")
            confidence = b.slider(
                "Confianza recomendada (%)",
                50,
                100,
                80,
                key="nb_conf",
                help="Probabilidad estimada por ti o por el tipster. 70–74%=5%, 75–79%=10%, 80–84%=20%, 85–89%=25%, 90–100%=30%.",
            )

            base = staking_base(bets, cfg)
            profile_rows = get_stake_profile(base, cfg)
            profile = {row["unit"]: row["cash"] for row in profile_rows}
            suggested_unit = unit_for_confidence(confidence)
            auto_stake = st.toggle(
                "Calcular unidad y stake automáticamente",
                value=True,
                key="nb_auto_stake",
                help="Usa exactamente el porcentaje acordado sobre el bank definido por el modo de staking.",
            )

            if auto_stake:
                unit = suggested_unit
                stake = profile.get(unit, 0.0)
                plan_pct = _plan_percent(unit, cfg)
                m1, m2, m3 = st.columns(3)
                m1.metric("Unidad automática", unit)
                m2.metric("Porcentaje exacto", f"{plan_pct:.0%}" if unit != "—" else "0%")
                m3.metric("Stake exacto", ui.money(stake, currency))
                if unit == "—":
                    st.warning("Con menos de 70% de confianza el plan recomienda no apostar.", icon=":material/warning:")
                else:
                    st.caption(
                        f"Cálculo: {plan_pct:.0%} × {ui.money(base, currency)} = **{ui.money(stake, currency)}** "
                        f"(staking {cfg.staking_mode})."
                    )
            else:
                a, b = st.columns(2)
                default_unit = suggested_unit if suggested_unit in UNIT_TYPES else "1U"
                unit = a.selectbox("Unidad manual", UNIT_TYPES, index=UNIT_TYPES.index(default_unit), key="nb_unit")
                exact_unit = b.toggle("Usar porcentaje exacto", value=True, key="nb_exact_unit")
                plan_pct = _plan_percent(unit, cfg)
                if exact_unit:
                    stake = profile[unit]
                    st.caption(f"{unit} = {plan_pct:.0%} × {ui.money(base, currency)} = **{ui.money(stake, currency)}**")
                else:
                    stake = st.number_input(
                        f"Stake manual ({currency})",
                        min_value=1.0,
                        value=float(profile[unit]),
                        step=1000.0,
                        format="%.2f",
                        key="nb_manual_stake",
                    )
                    st.caption("El asesor avisará si el valor no coincide con el porcentaje de la unidad.")

            ui.section_title("3. Estado y notas", "assignment")
            a, b = st.columns(2)
            status = a.selectbox("Estado", list(STATUSES), format_func=STATUSES.get, key="nb_status")
            closing = b.number_input(
                "Cuota de cierre (opcional)",
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.2f",
                key="nb_closing",
                help="Para medir el CLV. Déjala en 0 si aún no la conoces.",
            )
            notes = st.text_area("Notas", key="nb_notes", placeholder="Razonamiento, tipster, fuente…", height=80)

    advice = advise_stake(odds, confidence, stake, bets, cfg, selected_unit=unit)
    with advice_col:
        ui.section_title("Asesor de riesgo", "shield", "Se recalcula al cambiar cualquier dato.")
        titles = {"success": "Dentro del plan", "warning": "Revisa antes de entrar", "danger": "Riesgo alto: no recomendada"}
        ui.risk_card(advice.level, titles[advice.level], [
            ("Prob. implícita", f"{advice.implied_prob:.1f}%"),
            ("Recomendación", f"{advice.estimated_prob:.0f}%"),
            ("Valor esperado", ui.money(advice.expected_value, currency, signed=True)),
            ("Kelly completo", f"{advice.kelly_full * 100:.1f}%"),
            (f"Kelly ×{cfg.kelly_fraction:g}", ui.money(advice.kelly_stake, currency)),
            ("Plan acordado", f"{unit} · {_plan_percent(unit, cfg):.0%}" if unit != "—" else "No apostar"),
        ], advice.alerts)
        st.plotly_chart(charts.kelly_gauge(advice.edge), width="stretch", config={"displayModeBar": False})

        missing = not event.strip() or not market.strip() or not selection.strip()
        blocked = stake <= 0 or stake > cfg.max_special_stake or missing
        if st.button("Guardar apuesta", type="primary", icon=":material/save:", width="stretch", disabled=blocked):
            try:
                bet_id = db.add_bet(
                    bet_date=st.session_state["nb_date"].isoformat(),
                    sport=sport,
                    market=market,
                    event_name=event,
                    selection=selection,
                    odds=odds,
                    stake=stake,
                    confidence=confidence,
                    unit_type=unit,
                    status=status,
                    closing_odds=closing or None,
                    notes=notes,
                )
            except ValueError as exc:
                st.error(str(exc), icon=":material/error:")
            else:
                _reset()
                ui.flash(f"Apuesta #{bet_id} guardada con {unit} ({_plan_percent(unit, cfg):.0%}).")
                st.rerun()
        if missing:
            st.caption("Completa evento, mercado y selección para guardar.")
        elif stake <= 0:
            st.caption("El plan no permite guardar una apuesta automática por debajo de 70% de confianza.")
        elif stake > cfg.max_special_stake:
            st.caption(f"Bloqueado: el stake supera el máximo especial de {ui.money(cfg.max_special_stake, currency)}.")
