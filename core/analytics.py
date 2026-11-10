"""Métricas de rendimiento, plan de staking y asesor de riesgo (funciones puras, sin Streamlit).

Definiciones usadas (estándar del sector):
- **Yield** = beneficio neto / total apostado (rentabilidad por peso arriesgado).
- **ROI del bank** = beneficio neto / bankroll inicial (crecimiento del capital).
- **Win rate** = ganadas / (ganadas + perdidas); las nulas no cuentan.
- **Kelly** = (p·b − q) / b con b = cuota − 1; se recomienda una fracción (¼ Kelly por defecto).
- **CLV** = cuota tomada / cuota de cierre − 1 (positivo = se ganó al mercado).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional

import pandas as pd

from core.models import LOSS_STATUSES, SETTLED_STATUSES, WIN_STATUSES, BankSettings

# Plan acordado: cada nivel de confianza aplica un porcentaje exacto del bank.
# Los intervalos no se solapan: 70–74 → 5%, 75–79 → 10%, 80–84 → 20%,
# 85–89 → 25% y 90–100 → 30%. Por debajo de 70% no se recomienda apostar.
STAKE_RULES: Dict[str, Dict[str, float]] = {
    "1U": {"confidence": 70, "max_confidence": 74, "pct": 0.05, "label": "Base"},
    "2U": {"confidence": 75, "max_confidence": 79, "pct": 0.10, "label": "Moderado"},
    "3U": {"confidence": 80, "max_confidence": 84, "pct": 0.20, "label": "Alto"},
    "4U": {"confidence": 85, "max_confidence": 89, "pct": 0.25, "label": "Máximo"},
    "Whale": {"confidence": 90, "max_confidence": 100, "pct": 0.30, "label": "Especial"},
}
WHALE_CONFIDENCE = 90
ODDS_BANDS = [(1.0, 1.5, "1.01–1.50"), (1.5, 2.0, "1.51–2.00"), (2.0, 3.0, "2.01–3.00"), (3.0, 1e9, "3.01+")]


def safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def kelly_fraction(decimal_odds: float, probability: float) -> float:
    """Fracción de Kelly completa (0 si no hay ventaja)."""
    if decimal_odds <= 1.0 or not 0 < probability < 1:
        return 0.0
    b = decimal_odds - 1.0
    return max(0.0, min((probability * b - (1 - probability)) / b, 1.0))


def implied_probability(decimal_odds: float) -> float:
    return safe_divide(1.0, decimal_odds)


def bets_frame(bets: Iterable[dict]) -> pd.DataFrame:
    """DataFrame tipado de apuestas (vacío con columnas si no hay datos)."""
    df = pd.DataFrame(list(bets))
    cols = ["id", "bet_date", "sport", "market", "event_name", "selection", "odds", "stake",
            "confidence", "unit_type", "status", "net_profit", "closing_odds", "notes"]
    for col in cols:
        if col not in df.columns:
            df[col] = pd.Series(dtype="object")
    for col in ("odds", "stake", "confidence", "net_profit", "closing_odds"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["bet_date"] = pd.to_datetime(df["bet_date"], errors="coerce")
    return df


def current_bankroll(bets: Iterable[dict], settings: BankSettings) -> float:
    df = bets_frame(bets)
    return round(settings.base_bankroll + float(df["net_profit"].fillna(0).sum()), 2)


def available_bankroll(bets: Iterable[dict], settings: BankSettings) -> float:
    """Capital utilizable después de separar la reserva protegida."""
    return round(max(current_bankroll(bets, settings) - settings.protected_reserve, 0.0), 2)


def staking_base(bets: Iterable[dict], settings: BankSettings) -> float:
    """Bank disponible sobre el que se calculan las unidades según el modo de staking."""
    if settings.staking_mode == "dinamico":
        return available_bankroll(bets, settings)
    return max(settings.base_bankroll - settings.protected_reserve, 0.0)


def stake_for_unit(unit: str, bankroll: float, settings: Optional[BankSettings] = None) -> float:
    """Devuelve el porcentaje acordado de una unidad, con precisión de centavos.

    Whale conserva el porcentaje máximo configurado y el tope absoluto. Las demás
    unidades siempre usan 5%, 10%, 20%, 25% y 30%; no se interpolan ni aproximan.
    """
    settings = settings or BankSettings()
    rule = STAKE_RULES.get(unit)
    if rule is None:
        return 0.0
    stake = Decimal(str(bankroll)) * Decimal(str(rule["pct"]))
    if unit == "Whale":
        stake = min(stake, Decimal(str(settings.max_special_stake)))
    return float(stake.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def get_stake_profile(bankroll: float, settings: Optional[BankSettings] = None) -> List[dict]:
    settings = settings or BankSettings()
    return [
        {"unit": unit, "label": rule["label"], "confidence": rule["confidence"],
         "max_confidence": rule["max_confidence"], "pct": rule["pct"],
         "cash": stake_for_unit(unit, bankroll, settings)}
        for unit, rule in STAKE_RULES.items()
    ]


def unit_for_confidence(confidence: float) -> str:
    """Mapeo exacto de la recomendación del usuario a la unidad acordada."""
    confidence = float(confidence)
    for unit, rule in STAKE_RULES.items():
        if rule["confidence"] <= confidence <= rule["max_confidence"]:
            return unit
    return "—"


def unit_for_percentage(percentage: float) -> str:
    """Unidad cuyo porcentaje acordado coincide exactamente; «—» si no coincide."""
    percentage = float(percentage)
    for unit, rule in STAKE_RULES.items():
        if abs(percentage - rule["pct"] * 100) < 0.001:
            return unit
    return "—"


def nearest_unit_for_stake(stake: float, bankroll: float) -> str:
    """Nivel acordado más cercano a un monto recomendado por un tipster."""
    if bankroll <= 0 or stake <= 0:
        return "—"
    percentage = stake / bankroll
    return min(STAKE_RULES, key=lambda unit: abs(STAKE_RULES[unit]["pct"] - percentage))


@dataclass
class RecommendationPlan:
    unit: str
    confidence: float
    percentage: float
    recommended_stake: float
    final_stake: float
    adjustments: List[Dict[str, str]] = field(default_factory=list)


RECOMMENDATION_MODES = {
    "confidence": "Nivel de confianza",
    "percentage": "Porcentaje del bank",
    "amount": "Monto recomendado",
}


def plan_recommendation(mode: str, value: float, bankroll: float,
                        settings: Optional[BankSettings] = None) -> RecommendationPlan:
    """Normaliza lo recibido del tipster y aplica los límites configurados.

    Confianza y porcentaje siempre se convierten al porcentaje exacto acordado. Un monto
    directo se conserva como recomendación y se asocia al nivel más cercano. El stake final
    nunca excede el capital disponible, el límite por apuesta ni el tope monetario especial.
    """
    settings = settings or BankSettings()
    if mode not in RECOMMENDATION_MODES:
        raise ValueError("Tipo de recomendación desconocido.")
    if bankroll <= 0:
        return RecommendationPlan("—", 0, 0, 0, 0,
                                  [{"tone": "danger", "text": "No hay bank disponible después de la reserva."}])

    if mode == "confidence":
        unit = unit_for_confidence(value)
        if unit == "—":
            return RecommendationPlan(unit, float(value), 0, 0, 0,
                                      [{"tone": "warning", "text": "Menos de 70%: el plan recomienda no apostar."}])
        rule = STAKE_RULES[unit]
        percentage = rule["pct"] * 100
        recommended = stake_for_unit(unit, bankroll, settings)
        confidence = float(value)
    elif mode == "percentage":
        unit = unit_for_percentage(value)
        if unit == "—":
            raise ValueError("El porcentaje debe ser uno de los acordados: 5%, 10%, 20%, 25% o 30%.")
        rule = STAKE_RULES[unit]
        percentage = float(value)
        recommended = stake_for_unit(unit, bankroll, settings)
        confidence = rule["confidence"]
    else:
        recommended = round(float(value), 2)
        if recommended <= 0:
            raise ValueError("El monto recomendado debe ser mayor que cero.")
        unit = nearest_unit_for_stake(recommended, bankroll)
        rule = STAKE_RULES[unit]
        percentage = recommended / bankroll * 100
        confidence = rule["confidence"]

    final = recommended
    adjustments: List[Dict[str, str]] = []
    configured_cap = bankroll * settings.max_risk_ratio
    caps = [(bankroll, "capital disponible"), (configured_cap, f"límite por apuesta ({settings.max_risk_ratio:.0%})"),
            (settings.max_special_stake, "tope monetario especial")]
    cap, cap_label = min(caps, key=lambda item: item[0])
    if final > cap:
        final = cap
        adjustments.append({"tone": "warning", "text": f"Stake reducido al {cap_label}."})
    if mode == "amount":
        exact = STAKE_RULES[unit]["pct"] * 100
        if abs(percentage - exact) > 0.01:
            adjustments.append({"tone": "info", "text":
                                f"El monto equivale a {percentage:.2f}% del bank; el nivel acordado más cercano es {unit} ({exact:.0f}%)."})
    return RecommendationPlan(unit, confidence, round(percentage, 2), round(recommended, 2), round(final, 2), adjustments)


def _streaks(results: List[str]) -> Dict[str, object]:
    best_win = best_loss = run = 0
    current_kind = None
    for res in results:
        kind = "W" if res in WIN_STATUSES else "L" if res in LOSS_STATUSES else None
        if kind is None:
            continue
        run = run + 1 if kind == current_kind else 1
        current_kind = kind
        if kind == "W":
            best_win = max(best_win, run)
        else:
            best_loss = max(best_loss, run)
    return {"current": f"{run}{current_kind}" if current_kind else "—", "best_win": best_win, "best_loss": best_loss}


def summarize_bets(bets: Iterable[dict], settings: Optional[BankSettings] = None) -> dict:
    settings = settings or BankSettings()
    df = bets_frame(bets)
    settled = df[df["status"].isin(SETTLED_STATUSES)].sort_values(["bet_date", "id"])
    pending = df[df["status"] == "pending"]

    total_staked = float(settled["stake"].sum())
    net_profit = float(settled["net_profit"].sum())
    wins = int(settled["status"].isin(WIN_STATUSES).sum())
    losses = int(settled["status"].isin(LOSS_STATUSES).sum())
    voids = int((settled["status"] == "void").sum())
    bank_now = settings.base_bankroll + net_profit
    bank_available = max(bank_now - settings.protected_reserve, 0.0)
    curve = build_cumulative_bankroll(bets, settings)
    drawdown = max_drawdown([p["bankroll"] for p in curve])
    target_profit = settings.breakeven_target - settings.base_bankroll
    goal_target = settings.base_bankroll + settings.profit_target
    stop_loss_limit = settings.base_bankroll * settings.stop_loss_ratio
    clv = settled.dropna(subset=["closing_odds"])
    clv_avg = float((clv["odds"] / clv["closing_odds"] - 1).mean() * 100) if not clv.empty else None
    kelly_ref = (
        float(settled.apply(lambda r: kelly_fraction(r["odds"], r["confidence"] / 100), axis=1).mean())
        if not settled.empty else 0.0
    )
    open_exposure = float(pending["stake"].sum())

    return {
        "total_bets": int(len(df)),
        "settled_bets": int(len(settled)),
        "pending_bets": int(len(pending)),
        "wins": wins,
        "losses": losses,
        "voids": voids,
        "total_staked": round(total_staked, 2),
        "net_profit": round(net_profit, 2),
        "yield": round(safe_divide(net_profit, total_staked) * 100, 2),
        "roi_bank": round(safe_divide(net_profit, settings.base_bankroll) * 100, 2),
        "win_rate": round(safe_divide(wins, wins + losses) * 100, 2),
        "avg_odds": round(float(settled["odds"].mean()), 2) if not settled.empty else 0.0,
        "avg_stake": round(float(settled["stake"].mean()), 2) if not settled.empty else 0.0,
        "current_bankroll": round(bank_now, 2),
        "available_bankroll": round(bank_available, 2),
        "protected_reserve": round(settings.protected_reserve, 2),
        "bankroll_after_subscription": round(bank_now - settings.subscription_cost, 2),
        "breakeven_gap": round(max(settings.breakeven_target - bank_now, 0.0), 2),
        "breakeven_progress": round(min(max(safe_divide(net_profit, target_profit), 0.0), 1.0) * 100, 1)
        if target_profit > 0 else 100.0,
        "profit_target": round(settings.profit_target, 2),
        "goal_bankroll": round(goal_target, 2),
        "goal_gap": round(max(goal_target - bank_now, 0.0), 2),
        "goal_progress": round(min(max(safe_divide(net_profit, settings.profit_target), 0.0), 1.0) * 100, 1)
        if settings.profit_target > 0 else 100.0,
        "stop_loss_limit": round(stop_loss_limit, 2),
        "stop_loss_remaining": round(max(stop_loss_limit + min(net_profit, 0.0), 0.0), 2),
        "max_drawdown": round(drawdown["amount"], 2),
        "max_drawdown_pct": round(drawdown["pct"] * 100, 2),
        "open_exposure": round(open_exposure, 2),
        "open_exposure_pct": round(safe_divide(open_exposure, max(bank_available, 1)) * 100, 2),
        "kelly_reference": round(kelly_ref, 4),
        "clv_avg": round(clv_avg, 2) if clv_avg is not None else None,
        "streaks": _streaks(list(settled["status"])),
    }


def build_cumulative_bankroll(bets: Iterable[dict], settings: Optional[BankSettings] = None) -> List[dict]:
    """Curva del bank apuesta a apuesta (solo liquidadas, en orden cronológico)."""
    settings = settings or BankSettings()
    df = bets_frame(bets)
    df = df[df["status"].isin(SETTLED_STATUSES)].dropna(subset=["bet_date"]).sort_values(["bet_date", "id"])
    running = settings.base_bankroll
    rows = [{"n": 0, "date": None, "bankroll": round(running, 2), "net": 0.0, "label": "Inicio"}]
    for i, (_, item) in enumerate(df.iterrows(), start=1):
        running += float(item["net_profit"])
        rows.append({"n": i, "date": item["bet_date"].strftime("%Y-%m-%d"), "bankroll": round(running, 2),
                     "net": float(item["net_profit"]), "label": str(item["event_name"])})
    return rows


def max_drawdown(values: List[float]) -> Dict[str, float]:
    peak, worst, worst_pct = float("-inf"), 0.0, 0.0
    for value in values:
        peak = max(peak, value)
        drop = peak - value
        if drop > worst:
            worst, worst_pct = drop, safe_divide(drop, peak)
    return {"amount": worst, "pct": worst_pct}


def breakdown(bets: Iterable[dict], by: str) -> pd.DataFrame:
    """Rendimiento agrupado por 'sport', 'market', 'unit_type' u 'odds_band'."""
    df = bets_frame(bets)
    df = df[df["status"].isin(SETTLED_STATUSES)].copy()
    if df.empty:
        return pd.DataFrame(columns=[by, "apuestas", "apostado", "neto", "yield", "win_rate"])
    if by == "odds_band":
        df["odds_band"] = df["odds"].apply(lambda o: next(lbl for lo, hi, lbl in ODDS_BANDS if lo < o <= hi))
    df["is_win"] = df["status"].isin(WIN_STATUSES)
    df["is_loss"] = df["status"].isin(LOSS_STATUSES)
    grouped = df.groupby(by).agg(apuestas=("id", "count"), apostado=("stake", "sum"), neto=("net_profit", "sum"),
                                 wins=("is_win", "sum"), losses=("is_loss", "sum")).reset_index()
    grouped["yield"] = (grouped["neto"] / grouped["apostado"] * 100).round(2)
    decided = (grouped["wins"] + grouped["losses"]).astype(float)
    grouped["win_rate"] = (grouped["wins"].astype(float) / decided.where(decided > 0) * 100).round(1)
    return grouped.drop(columns=["wins", "losses"]).sort_values("neto", ascending=False).reset_index(drop=True)


def monthly_summary(bets: Iterable[dict]) -> pd.DataFrame:
    df = bets_frame(bets)
    df = df[df["status"].isin(SETTLED_STATUSES)].dropna(subset=["bet_date"])
    if df.empty:
        return pd.DataFrame(columns=["mes", "apuestas", "apostado", "neto", "yield"])
    df["mes"] = df["bet_date"].dt.to_period("M").astype(str)
    out = df.groupby("mes").agg(apuestas=("id", "count"), apostado=("stake", "sum"), neto=("net_profit", "sum")).reset_index()
    out["yield"] = (out["neto"] / out["apostado"] * 100).round(2)
    return out


# --------------------------------------------------------------------------- asesor de stake

@dataclass
class StakeAdvice:
    implied_prob: float
    estimated_prob: float
    edge: float
    expected_value: float
    kelly_full: float
    kelly_stake: float
    suggested_unit: str
    unit_stake: float
    alerts: List[Dict[str, str]] = field(default_factory=list)

    @property
    def level(self) -> str:
        tones = {a["tone"] for a in self.alerts}
        return "danger" if "danger" in tones else "warning" if "warning" in tones else "success"


def advise_stake(odds: float, confidence: float, stake: float, bets: Iterable[dict],
                 settings: Optional[BankSettings] = None, selected_unit: Optional[str] = None) -> StakeAdvice:
    """Evalúa una apuesta antes de registrarla: ventaja, Kelly fraccional y reglas del plan.

    ``selected_unit`` es opcional para mantener compatibilidad. Cuando la interfaz la envía,
    el asesor también detecta una unidad distinta de la recomendada o un stake que no coincide
    exactamente con el porcentaje acordado.
    """
    settings = settings or BankSettings()
    bets = list(bets)
    bank_now = available_bankroll(bets, settings)
    base = staking_base(bets, settings)
    p = confidence / 100
    implied = implied_probability(odds)
    k_full = kelly_fraction(odds, p)
    unit = unit_for_confidence(confidence)
    profile = {row["unit"]: row["cash"] for row in get_stake_profile(base, settings)}
    pending_exposure = float(bets_frame(bets).query("status == 'pending'")["stake"].sum())

    alerts: List[Dict[str, str]] = []
    if stake > settings.max_special_stake:
        alerts.append({"tone": "danger", "text": f"Supera el stake especial máximo ({settings.max_special_stake:,.0f})."})
    if stake > bank_now * settings.max_risk_ratio:
        alerts.append({"tone": "danger",
                       "text": f"Arriesga más del {settings.max_risk_ratio:.0%} del bank actual ({bank_now * settings.max_risk_ratio:,.0f})."})
    if stake > bank_now:
        alerts.append({"tone": "danger", "text": "El stake es mayor que el bank disponible."})
    if (pending_exposure + stake) > bank_now * settings.max_open_exposure:
        alerts.append({"tone": "warning",
                       "text": f"La exposición abierta superaría el {settings.max_open_exposure:.0%} del bank."})
    if k_full == 0:
        alerts.append({"tone": "warning", "text": "Sin ventaja: la confianza no supera la probabilidad implícita de la cuota."})
    if unit == "—":
        alerts.append({"tone": "warning", "text": f"Confianza menor a {STAKE_RULES['1U']['confidence']}%: el plan no recomienda entrar."})
    else:
        effective_unit = selected_unit or unit
        if selected_unit and selected_unit != unit:
            alerts.append({"tone": "warning", "text": f"La confianza de {confidence:.0f}% recomienda {unit}, no {selected_unit}."})
        planned_stake = profile.get(effective_unit, 0.0)
        if abs(stake - planned_stake) > 0.01:
            planned_pct = STAKE_RULES.get(effective_unit, {}).get("pct", 0)
            alerts.append({"tone": "warning", "text":
                           f"El stake no coincide con {effective_unit}: debe ser exactamente {planned_pct:.0%} del bank ({planned_stake:,.2f})."})

    return StakeAdvice(
        implied_prob=round(implied * 100, 2),
        estimated_prob=round(p * 100, 2),
        edge=round((p - implied) * 100, 2),
        expected_value=round(stake * (p * (odds - 1) - (1 - p)), 2),
        kelly_full=round(k_full, 4),
        kelly_stake=round(max(bank_now, 0) * k_full * settings.kelly_fraction, 2),
        suggested_unit=unit,
        unit_stake=profile.get(unit, 0.0),
        alerts=alerts,
    )
