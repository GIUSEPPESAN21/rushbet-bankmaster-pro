from __future__ import annotations

from typing import Dict, Iterable, List

import pandas as pd

BASE_BANKROLL = 250000.0
SUBSCRIPTION_COST = 120000.0
BREAKEVEN_TARGET = 370000.0
SPECIAL_MAX_STAKE = 150000.0

STAKE_RULES = {
    "1U": {"confidence": 70, "pct": 0.02, "cash": 5000.0},
    "2U": {"confidence": 75, "pct": 0.04, "cash": 10000.0},
    "3U": {"confidence": 85, "pct": 0.06, "cash": 15000.0},
    "4U": {"confidence": 90, "pct": 0.10, "cash": 25000.0},
}


def get_stake_profile(bankroll: float) -> Dict[str, Dict[str, float]]:
    profile = {}
    for label, schema in STAKE_RULES.items():
        profile[label] = {
            "confidence": schema["confidence"],
            "pct": schema["pct"],
            "cash": round(bankroll * schema["pct"], 2),
        }
    profile["whale"] = {
        "confidence": 95,
        "pct": 0.10,
        "cash": min(float(bankroll * 0.10), SPECIAL_MAX_STAKE),
    }
    return profile


def safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def calculate_roi(net_profit: float, total_staked: float) -> float:
    return (net_profit / total_staked * 100) if total_staked else 0.0


def calculate_yield(net_profit: float, bankroll: float) -> float:
    return (net_profit / bankroll * 100) if bankroll else 0.0


def calculate_win_rate(wins: int, losses: int, pushes: int = 0) -> float:
    total = wins + losses + pushes
    return (wins / total * 100) if total else 0.0


def kelly_fraction(decimal_odds: float, probability: float) -> float:
    if decimal_odds <= 1.0 or probability <= 0 or probability >= 1:
        return 0.0
    b = decimal_odds - 1.0
    fraction = (probability * b - (1 - probability)) / b
    return max(0.0, min(fraction, 1.0))


def summarize_bets(bets: Iterable[dict], bankroll: float = BASE_BANKROLL) -> dict:
    bets_df = pd.DataFrame(bets)
    if bets_df.empty:
        return {
            "total_bets": 0,
            "settled_bets": 0,
            "wins": 0,
            "losses": 0,
            "voids": 0,
            "total_staked": 0.0,
            "net_profit": 0.0,
            "roi": 0.0,
            "yield": 0.0,
            "win_rate": 0.0,
            "breakeven_gap": round(max(BREAKEVEN_TARGET - bankroll, 0.0), 2),
            "bankroll_after_subscription": round(bankroll - SUBSCRIPTION_COST, 2),
            "current_bankroll": round(bankroll, 2),
            "kelly_reference": 0.0,
        }

    settled = bets_df[bets_df["status"].isin(["won", "lost", "void"])].copy()
    total_staked = float(settled["stake"].sum()) if not settled.empty else 0.0
    net_profit = float(settled["net_profit"].sum()) if not settled.empty else 0.0
    wins = int((settled["result"] == "won").sum())
    losses = int((settled["result"] == "lost").sum())
    voids = int((settled["result"] == "void").sum())
    roi = calculate_roi(net_profit, total_staked)
    yield_pct = calculate_yield(net_profit, bankroll)
    win_rate = calculate_win_rate(wins, losses, voids)
    breakeven_gap = max(BREAKEVEN_TARGET - (bankroll + net_profit), 0.0)

    if not settled.empty:
        kelly_reference = float(
            settled.apply(
                lambda row: kelly_fraction(float(row["odds"]), float(row["confidence"]) / 100.0),
                axis=1,
            ).mean()
        )
    else:
        kelly_reference = 0.0

    summary = {
        "total_bets": int(len(bets_df)),
        "settled_bets": int(len(settled)),
        "wins": wins,
        "losses": losses,
        "voids": voids,
        "total_staked": round(total_staked, 2),
        "net_profit": round(net_profit, 2),
        "roi": round(roi, 2),
        "yield": round(yield_pct, 2),
        "win_rate": round(win_rate, 2),
        "breakeven_gap": round(breakeven_gap, 2),
        "bankroll_after_subscription": round(bankroll - SUBSCRIPTION_COST, 2),
        "current_bankroll": round(bankroll, 2),
        "kelly_reference": round(kelly_reference, 4),
    }
    return summary


def build_cumulative_bankroll(bets: Iterable[dict], bankroll: float = BASE_BANKROLL) -> List[dict]:
    bets_df = pd.DataFrame(bets)
    if bets_df.empty:
        return [{"date": "Inicio", "bankroll": bankroll}]

    bets_df["bet_date"] = pd.to_datetime(bets_df["bet_date"], errors="coerce")
    bets_df = bets_df.dropna(subset=["bet_date"]).sort_values("bet_date").copy()
    running_bankroll = bankroll
    rows = [{"date": "Inicio", "bankroll": round(running_bankroll, 2)}]
    for _, item in bets_df.iterrows():
        running_bankroll += float(item["net_profit"])
        rows.append({
            "date": item["bet_date"].strftime("%Y-%m-%d"),
            "bankroll": round(running_bankroll, 2),
        })
    return rows
