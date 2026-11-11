"""Dashboard ejecutivo: hero del bank, indicadores, curva, últimas apuestas y escalera de stakes."""

from __future__ import annotations

import streamlit as st

from core.analytics import build_cumulative_bankroll, get_stake_profile, staking_base, summarize_bets
from core.models import STATUS_TONES, STATUSES
from ui import charts
from ui import components as ui
from ui.state import load, load_withdrawals


def render() -> None:
    bets, cfg = load()
    withdrawals = load_withdrawals()
    m = summarize_bets(bets, cfg, withdrawals)
    c = cfg.currency

    ui.page_header("Dashboard ejecutivo", "Estado del capital, rendimiento y disciplina del plan.", "space_dashboard",
                   badges=[{"text": f"{m['pending_bets']} abiertas", "tone": "info", "icon": "schedule"},
                           {"text": f"Racha {m['streaks']['current']}", "tone": "neutral", "icon": "bolt"}])

    ui.bank_hero(m["current_bankroll"], m["net_profit"], m["roi_bank"], m["breakeven_progress"], m["breakeven_gap"],
                 cfg.breakeven_target, c,
                 badges=[{"text": f"Inicial {ui.money(cfg.base_bankroll, c)}", "icon": "account_balance"},
                         {"text": f"Suscripción {ui.money(cfg.subscription_cost, c)}", "icon": "receipt_long"},
                         {"text": f"Staking {cfg.staking_mode}", "icon": "tune"}])

    ui.stat_cards([
        {"label": "Yield", "value": ui.pct(m["yield"], signed=True), "icon": "percent", "tone": ui.tone_for(m["yield"]),
         "help": f"Sobre {ui.money(m['total_staked'], c)} apostados"},
        {"label": "Win rate", "value": ui.pct(m["win_rate"], digits=1), "icon": "emoji_events", "tone": "info",
         "help": f"{m['wins']} G · {m['losses']} P · {m['voids']} N"},
        {"label": "Máx. drawdown", "value": ui.pct(-m["max_drawdown_pct"], digits=1) if m["max_drawdown_pct"] else "0%",
         "icon": "trending_down", "tone": "danger" if m["max_drawdown_pct"] > 20 else "warning" if m["max_drawdown_pct"] else "neutral",
         "help": ui.money(m["max_drawdown"], c)},
        {"label": "Exposición abierta", "value": ui.money(m["open_exposure"], c), "icon": "hourglass_top",
         "tone": "danger" if m["open_exposure_pct"] > cfg.max_open_exposure * 100 else "info",
         "help": f"{m['open_exposure_pct']:.1f}% del bank (límite {cfg.max_open_exposure:.0%})"},
        {"label": "Cuota media", "value": f"{m['avg_odds']:.2f}", "icon": "query_stats", "tone": "neutral",
         "help": f"Stake medio {ui.money(m['avg_stake'], c)}"},
        {"label": "CLV medio", "value": ui.pct(m["clv_avg"], signed=True) if m["clv_avg"] is not None else "—",
         "icon": "compare_arrows", "tone": ui.tone_for(m["clv_avg"] or 0), "help": "Cuota tomada vs. cierre"},
    ])

    ui.section_title("Capital vs. ganancias", "savings",
                     "Las ganancias no se reinvierten: se separan para cubrir tus gastos.")
    ui.stat_cards([
        {"label": "Capital de apuesta", "value": ui.money(m["capital_now"], c), "icon": "account_balance",
         "tone": "info", "help": "Solo baja con pérdidas; las ganancias no lo aumentan"},
        {"label": "Disponible para apostar", "value": ui.money(m["available_to_stake"], c), "icon": "payments",
         "tone": "success", "help": f"Resta {ui.money(m['open_exposure'], c)} en apuestas pendientes"},
        {"label": "Ganancias disponibles", "value": ui.money(m["available_earnings"], c), "icon": "savings",
         "tone": "success", "help": f"Generadas {ui.money(m['gross_earnings'], c)} · Retiradas {ui.money(m['total_withdrawn'], c)}"},
        {"label": "Meta de gastos del mes", "value": ui.money(m["monthly_expense_goal"], c) if m["monthly_expense_goal"] else "Sin definir",
         "icon": "receipt_long", "tone": "neutral",
         "help": f"Cubierto {m['expense_goal_progress']:.0f}%" if m["monthly_expense_goal"] else "Config. en Configuración"},
    ])

    if not bets:
        ui.empty_state("Aún no hay apuestas", "Registra la primera en «Nueva apuesta» para activar el panel.", "add_chart")
        _ladder(bets, cfg)
        return

    left, right = st.columns([1.7, 1], gap="medium")
    with left:
        st.plotly_chart(charts.bankroll_curve(build_cumulative_bankroll(bets, cfg), cfg.base_bankroll, cfg.breakeven_target),
                        width="stretch", config={"displayModeBar": False})
    with right:
        st.plotly_chart(charts.results_donut(m["wins"], m["losses"], m["voids"], m["pending_bets"]),
                        width="stretch", config={"displayModeBar": False})

    left, right = st.columns([1, 1], gap="medium")
    with left:
        ui.section_title("Últimos movimientos", "history")
        ui.timeline([
            {"title": f"{b['event_name']} · {b['selection']}",
             "meta": f"{b['bet_date']} · {b['sport']} · {b['market']} · @{b['odds']:.2f} · {STATUSES.get(b['status'], b['status'])}",
             "amount": ui.money(b["net_profit"], c, signed=True) if b["status"] != "pending" else ui.money(b["stake"], c),
             "tone": STATUS_TONES.get(b["status"], "neutral")}
            for b in bets[:7]
        ])
    with right:
        _ladder(bets, cfg)
    ui.footer()


def _ladder(bets, cfg) -> None:
    base = staking_base(bets, cfg)
    ui.section_title("Escalera de stakes", "stairs", f"Calculada sobre {ui.money(base, cfg.currency)} (modo {cfg.staking_mode}).")
    ui.stake_ladder(get_stake_profile(base, cfg), cfg.currency)
