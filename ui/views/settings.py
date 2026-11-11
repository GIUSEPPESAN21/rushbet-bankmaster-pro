"""Configuración simple del presupuesto, los objetivos y los límites de capital."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import streamlit as st

from core import database as db
from core.analytics import get_stake_profile, staking_base, summarize_bets
from core.models import STAKING_MODES, BankSettings
from ui import components as ui
from ui.state import load, load_withdrawals

PROFILES = {
    "Conservador": {"max_risk_ratio": 0.10, "max_open_exposure": 0.20, "stop_loss_ratio": 0.10},
    "Balanceado": {"max_risk_ratio": 0.20, "max_open_exposure": 0.30, "stop_loss_ratio": 0.15},
    "Plan acordado": {"max_risk_ratio": 0.30, "max_open_exposure": 0.30, "stop_loss_ratio": 0.20},
}


def _apply_profile(name: str, cfg: BankSettings) -> None:
    db.save_settings(replace(cfg, **PROFILES[name]))
    ui.flash(f"Perfil {name.lower()} aplicado.")
    st.rerun()


def render() -> None:
    bets, cfg = load()
    withdrawals = load_withdrawals()
    metrics = summarize_bets(bets, cfg, withdrawals)
    ui.show_flash()
    ui.page_header("Presupuesto y objetivos", "Ajusta el capital disponible y deja que la app aplique sus límites.", "tune")

    ui.stat_cards([
        {"label": "Bank actual", "value": ui.money(metrics["current_bankroll"], cfg.currency), "icon": "account_balance", "tone": "info"},
        {"label": "Reserva protegida", "value": ui.money(cfg.protected_reserve, cfg.currency), "icon": "lock", "tone": "neutral"},
        {"label": "Disponible para apostar", "value": ui.money(metrics["available_to_stake"], cfg.currency), "icon": "payments", "tone": "success",
         "help": "Ya descuenta apuestas pendientes; el capital no se toca hasta liquidarlas."},
        {"label": "Objetivo de bank", "value": ui.money(metrics["goal_bankroll"], cfg.currency), "icon": "flag", "tone": "info",
         "help": f"Faltan {ui.money(metrics['goal_gap'], cfg.currency)}"},
    ])

    ui.section_title("Perfiles rápidos", "speed", "Solo cambian los límites; nunca alteran apuestas existentes.")
    p1, p2, p3 = st.columns(3)
    if p1.button("Conservador", icon=":material/shield:", width="stretch",
                 help="10% máximo por apuesta · 20% exposición · stop-loss 10%"):
        _apply_profile("Conservador", cfg)
    if p2.button("Balanceado", icon=":material/balance:", width="stretch",
                 help="20% máximo por apuesta · 30% exposición · stop-loss 15%"):
        _apply_profile("Balanceado", cfg)
    if p3.button("Plan acordado", type="primary", icon=":material/bolt:", width="stretch",
                 help="30% máximo por apuesta · 30% exposición · stop-loss 20%"):
        _apply_profile("Plan acordado", cfg)
    st.caption("Los niveles 70→5%, 75→10%, 80→20%, 85→25% y 90→30% no cambian. "
               "Un perfil puede reducir el stake final para proteger el bank.")

    with st.form("settings_form"):
        ui.section_title("Presupuesto", "account_balance", "La reserva nunca se usa para calcular stakes.")
        a, b, d = st.columns(3)
        base = a.number_input("Bankroll inicial", min_value=10_000.0, value=cfg.base_bankroll,
                              step=10_000.0, format="%.2f")
        reserve = b.number_input("Reserva protegida", min_value=0.0, max_value=float(base),
                                 value=min(cfg.protected_reserve, base), step=5_000.0, format="%.2f",
                                 help="Capital que la plataforma aparta y no arriesga.")
        subscription = d.number_input("Costo de suscripción", min_value=0.0, value=cfg.subscription_cost,
                                      step=10_000.0, format="%.2f")
        st.info(f"Capital inicial utilizable: **{ui.money(base - reserve, cfg.currency)}**", icon=":material/savings:")

        ui.section_title("Objetivos", "flag", "Define recuperación y ganancia sin modificar el historial.")
        a, b, d = st.columns(3)
        breakeven = a.number_input("Objetivo de recuperación (bank)", min_value=10_000.0,
                                   value=cfg.breakeven_target, step=10_000.0, format="%.2f",
                                   help="Bank necesario para recuperar la inversión; suele ser bank inicial + suscripción.")
        profit_target = b.number_input("Ganancia objetivo", min_value=0.0, value=cfg.profit_target,
                                       step=10_000.0, format="%.2f",
                                       help="La meta de bank será bankroll inicial + esta ganancia.")
        expense_goal = d.number_input("Gasto fijo mensual a cubrir", min_value=0.0, value=cfg.monthly_expense_goal,
                                      step=10_000.0, format="%.2f",
                                      help="Lo que quieres cubrir con ganancias cada mes (arriendo, servicios…).")

        ui.section_title("Protección del capital", "shield")
        a, b, d = st.columns(3)
        max_special = a.number_input("Tope monetario por apuesta", min_value=1_000.0,
                                     value=cfg.max_special_stake, step=5_000.0, format="%.2f")
        risk = b.slider("Máximo por apuesta", 1, 50, int(round(cfg.max_risk_ratio * 100)), format="%d%%")
        exposure = d.slider("Exposición abierta máxima", 5, 100,
                            int(round(cfg.max_open_exposure * 100)), format="%d%%")
        a, b, d = st.columns(3)
        stop_loss = a.slider("Stop-loss del bank", 5, 50, int(round(cfg.stop_loss_ratio * 100)), format="%d%%",
                             help="Pérdida acumulada que indica detener apuestas y revisar el plan.")
        kelly = b.select_slider(
            "Fracción de Kelly", options=[0.1, 0.25, 0.5, 1.0],
            value=cfg.kelly_fraction if cfg.kelly_fraction in (0.1, 0.25, 0.5, 1.0) else 0.25,
            format_func=lambda value: {0.1: "1/10", 0.25: "1/4", 0.5: "1/2", 1.0: "Completo"}[value],
        )
        mode = d.selectbox("Cálculo de unidades", list(STAKING_MODES), format_func=STAKING_MODES.get,
                           index=list(STAKING_MODES).index(cfg.staking_mode))
        currency = st.text_input("Moneda", cfg.currency, max_chars=5)

        save = st.form_submit_button("Guardar presupuesto y objetivos", type="primary", icon=":material/save:")
        if save:
            db.save_settings(BankSettings(
                base_bankroll=base,
                subscription_cost=subscription,
                breakeven_target=breakeven,
                max_special_stake=max_special,
                max_risk_ratio=risk / 100,
                kelly_fraction=float(kelly),
                max_open_exposure=exposure / 100,
                protected_reserve=reserve,
                profit_target=profit_target,
                stop_loss_ratio=stop_loss / 100,
                staking_mode=mode,
                currency=(currency or "COP").strip().upper(),
                monthly_expense_goal=expense_goal,
            ))
            ui.flash("Presupuesto, objetivos y límites guardados.")
            st.rerun()

    if metrics["max_drawdown"] >= metrics["stop_loss_limit"] and metrics["stop_loss_limit"] > 0:
        st.error("Stop-loss alcanzado: pausa nuevas apuestas y revisa el plan.", icon=":material/emergency_home:")
    if cfg.breakeven_target < cfg.base_bankroll + cfg.subscription_cost:
        st.info("El objetivo de recuperación no cubre bank inicial + suscripción.", icon=":material/info:")

    base_now = staking_base(bets, cfg)
    ui.section_title("Stakes resultantes", "stairs", f"Calculados sobre {ui.money(base_now, cfg.currency)}")
    ui.stake_ladder(get_stake_profile(base_now, cfg), cfg.currency)

    _earnings_and_withdrawals(cfg, metrics, withdrawals)

    with st.expander("Zona de peligro", icon=":material/warning:"):
        st.write("Borra las apuestas y restablece la configuración. Descarga antes un respaldo en Historial.")
        sure = st.text_input("Escribe BORRAR para confirmar", key="reset_confirm")
        if st.button("Borrar todo", icon=":material/delete_forever:", disabled=sure != "BORRAR"):
            db.reset_db()
            ui.flash("Base de datos reiniciada.", "warning")
            st.rerun()


def _earnings_and_withdrawals(cfg: BankSettings, metrics: dict, withdrawals: list) -> None:
    currency = cfg.currency
    ui.section_title("Ganancias y retiros", "savings",
                     "Las ganancias de tus apuestas no se reinvierten: sepáralas aquí para cubrir gastos.")
    ui.stat_cards([
        {"label": "Ganancias disponibles", "value": ui.money(metrics["available_earnings"], currency),
         "icon": "savings", "tone": "success"},
        {"label": "Generadas en total", "value": ui.money(metrics["gross_earnings"], currency), "icon": "trending_up", "tone": "info"},
        {"label": "Retiradas en total", "value": ui.money(metrics["total_withdrawn"], currency), "icon": "payments", "tone": "neutral"},
        {"label": "Meta mensual cubierta", "value": f"{metrics['expense_goal_progress']:.0f}%" if cfg.monthly_expense_goal else "Sin meta",
         "icon": "flag", "tone": "info", "help": ui.money(metrics["expense_goal_gap"], currency) + " por cubrir" if cfg.monthly_expense_goal else None},
    ])

    with st.form("withdrawal_form", clear_on_submit=True):
        a, b, d = st.columns([1, 1, 2])
        w_date = a.date_input("Fecha", value=date.today(), format="YYYY-MM-DD", key="wd_date")
        amount = b.number_input(f"Monto a retirar ({currency})", min_value=1.0,
                                value=min(1000.0, max(metrics["available_earnings"], 1.0)),
                                step=1000.0, format="%.2f", key="wd_amount")
        note = d.text_input("Motivo (opcional)", placeholder="Arriendo, servicios, imprevisto…", key="wd_note")
        submit = st.form_submit_button("Registrar retiro", type="primary", icon=":material/payments:")
        if submit:
            if amount > metrics["available_earnings"]:
                st.error(f"Solo tienes {ui.money(metrics['available_earnings'], currency)} disponibles en ganancias.",
                         icon=":material/error:")
            else:
                db.add_withdrawal(w_date.isoformat(), amount, note)
                ui.flash(f"Retiro de {ui.money(amount, currency)} registrado.")
                st.rerun()

    if withdrawals:
        with st.expander(f"Historial de retiros ({len(withdrawals)})", icon=":material/history:"):
            for w in withdrawals[:20]:
                c1, c2, c3 = st.columns([2, 5, 1])
                c1.write(ui.money(w["amount"], currency))
                c2.write(f"{w['w_date']} · {w['note'] or 'Sin motivo'}")
                if c3.button("", icon=":material/delete:", key=f"del_wd_{w['id']}"):
                    db.delete_withdrawal(w["id"])
                    ui.flash("Retiro eliminado.", "warning")
                    st.rerun()
