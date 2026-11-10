"""Configuración del plan de capital y reglas de riesgo."""

from __future__ import annotations

import streamlit as st

from core import database as db
from core.analytics import get_stake_profile, staking_base
from core.models import STAKING_MODES, BankSettings
from ui import components as ui
from ui.state import load


def render() -> None:
    bets, cfg = load()
    ui.show_flash()
    ui.page_header("Configuración", "Parámetros del bank, límites de riesgo y modo de staking.", "settings")

    with st.form("settings_form"):
        ui.section_title("Capital", "account_balance")
        a, b, d = st.columns(3)
        base = a.number_input("Bankroll inicial", min_value=10_000.0, value=cfg.base_bankroll, step=10_000.0, format="%.0f")
        sub = b.number_input("Costo de suscripción", min_value=0.0, value=cfg.subscription_cost, step=10_000.0, format="%.0f")
        target = d.number_input("Meta breakeven neta", min_value=10_000.0, value=cfg.breakeven_target, step=10_000.0, format="%.0f",
                                help="Bank que necesitas para recuperar la inversión (normalmente bank inicial + suscripción).")

        ui.section_title("Riesgo", "shield")
        a, b, d = st.columns(3)
        max_special = a.number_input("Stake especial máximo", min_value=1_000.0, value=cfg.max_special_stake, step=5_000.0, format="%.0f")
        risk = b.slider("Riesgo máximo por apuesta", 1, 25, int(round(cfg.max_risk_ratio * 100)), format="%d%%")
        exposure = d.slider("Exposición abierta máxima", 5, 100, int(round(cfg.max_open_exposure * 100)), format="%d%%")
        a, b = st.columns(2)
        kelly = a.select_slider("Fracción de Kelly", options=[0.1, 0.25, 0.5, 1.0], value=cfg.kelly_fraction
                                if cfg.kelly_fraction in (0.1, 0.25, 0.5, 1.0) else 0.25,
                                format_func=lambda v: {0.1: "1/10", 0.25: "1/4 (recomendado)", 0.5: "1/2", 1.0: "Completo"}[v])
        mode = b.radio("Modo de staking", list(STAKING_MODES), format_func=STAKING_MODES.get,
                       index=list(STAKING_MODES).index(cfg.staking_mode), horizontal=True,
                       help="Dinámico: las unidades crecen y se reducen con el bank actual (protege en drawdown).")
        currency = st.text_input("Moneda", cfg.currency, max_chars=5)
        if st.form_submit_button("Guardar configuración", type="primary", icon=":material/save:"):
            db.save_settings(BankSettings(
                base_bankroll=base, subscription_cost=sub, breakeven_target=target, max_special_stake=max_special,
                max_risk_ratio=risk / 100, kelly_fraction=float(kelly), max_open_exposure=exposure / 100,
                staking_mode=mode, currency=(currency or "COP").strip().upper(),
            ))
            ui.flash("Configuración guardada.")
            st.rerun()

    if cfg.max_special_stake > cfg.base_bankroll * cfg.max_risk_ratio:
        st.warning(f"Alerta roja: el stake especial ({ui.money(cfg.max_special_stake, cfg.currency)}) supera el "
                   f"{cfg.max_risk_ratio:.0%} del bankroll inicial. Las apuestas Whale quedan topadas al {cfg.max_risk_ratio:.0%}.",
                   icon=":material/report:")
    if cfg.breakeven_target < cfg.base_bankroll + cfg.subscription_cost:
        st.info("La meta de breakeven es menor que bank inicial + suscripción: no cubriría el costo del grupo.",
                icon=":material/info:")

    base_now = staking_base(bets, cfg)
    ui.section_title("Plan de unidades vigente", "stairs", f"Sobre {ui.money(base_now, cfg.currency)}")
    ui.stake_ladder(get_stake_profile(base_now, cfg), cfg.currency)

    with st.expander("Zona de peligro", icon=":material/warning:"):
        st.write("Borra todas las apuestas y restablece la configuración. Descarga antes un respaldo en Historial.")
        sure = st.text_input("Escribe BORRAR para confirmar", key="reset_confirm")
        if st.button("Borrar todo", icon=":material/delete_forever:", disabled=sure != "BORRAR"):
            db.reset_db()
            ui.flash("Base de datos reiniciada.", "warning")
            st.rerun()
