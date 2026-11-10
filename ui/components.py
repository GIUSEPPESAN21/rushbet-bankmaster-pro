"""Componentes visuales compartidos (contrato: las vistas los usan, assets/style.css los estiliza).

Todo texto se escapa con ``esc`` antes de incrustarlo en HTML: nombres de eventos y notas los
escribe el usuario. Los iconos son nombres de Material Symbols (la fuente que ya trae Streamlit).
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Iterable, List, Optional

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"
TONES = ("neutral", "info", "success", "warning", "danger")


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def money(value: float, currency: str = "COP", signed: bool = False) -> str:
    """Formato colombiano: $1.234.567 COP (signo opcional)."""
    value = float(value or 0)
    sign = "+" if signed and value > 0 else "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f} {currency}".replace(",", ".")


def pct(value: float, signed: bool = False, digits: int = 2) -> str:
    value = float(value or 0)
    return f"{value:+.{digits}f}%" if signed else f"{value:.{digits}f}%"


def tone_for(value: float) -> str:
    return "success" if value > 0 else "danger" if value < 0 else "neutral"


def _tone(tone: Optional[str]) -> str:
    return tone if tone in TONES else "neutral"


def icon_html(name: Optional[str]) -> str:
    return f'<span class="bm-ms" aria-hidden="true">{esc(name)}</span>' if name else ""


def _md(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def _css() -> str:
    return (ASSETS / "style.css").read_text(encoding="utf-8")


def load_theme() -> None:
    """Inyecta la hoja de estilos (una vez por ejecución de página)."""
    _md(f"<style>{_css()}</style>")


def badge_html(text, tone: str = "neutral", icon: Optional[str] = None) -> str:
    prefix = icon_html(icon)
    return f'<span class="bm-badge bm-badge--{_tone(tone)}">{prefix}{esc(text)}</span>'


def page_header(title: str, subtitle: Optional[str] = None, icon: Optional[str] = None,
                badges: Optional[List[dict]] = None) -> None:
    icon_part = f'<div class="bm-page-header__icon">{icon_html(icon)}</div>' if icon else ""
    sub = f'<div class="bm-page-header__subtitle">{esc(subtitle)}</div>' if subtitle else ""
    aside = "".join(badge_html(b["text"], b.get("tone", "neutral"), b.get("icon")) for b in (badges or []))
    aside_html = f'<div class="bm-page-header__aside">{aside}</div>' if aside else ""
    _md(f'<div class="bm-page-header">{icon_part}<div><div class="bm-page-header__title" role="heading" aria-level="1">'
        f'{esc(title)}</div>{sub}</div>{aside_html}</div>')


def bank_hero(bankroll: float, net_profit: float, roi_bank: float, progress: float, gap: float,
              target: float, currency: str, badges: Iterable[dict] = ()) -> None:
    """Banda principal del dashboard: bank actual, variación y progreso a la meta de breakeven."""
    up = net_profit >= 0
    delta_cls = "bm-hero__delta--up" if up else "bm-hero__delta--down"
    arrow = "trending_up" if up else "trending_down"
    meta = "".join(badge_html(b["text"], b.get("tone", "neutral"), b.get("icon")) for b in badges)
    progress = max(0.0, min(progress, 100.0))
    _md(
        f'<section class="bm-hero"><div class="bm-hero__body">'
        f'<div class="bm-hero__eyebrow">Bankroll actual</div>'
        f'<div class="bm-hero__value">{esc(money(bankroll, currency))}</div>'
        f'<span class="bm-hero__delta {delta_cls}">{icon_html(arrow)}{esc(money(net_profit, currency, signed=True))}'
        f' · {esc(pct(roi_bank, signed=True))}</span>'
        f'<div class="bm-hero__text">Gestión disciplinada del capital: cada apuesta se mide contra el plan de unidades y la meta neta.</div>'
        f'<div class="bm-hero__meta">{meta}</div></div>'
        f'<div class="bm-hero__side"><div class="bm-goal">'
        f'<div class="bm-goal__head"><span>Meta breakeven neta</span><span class="bm-goal__pct">{progress:.0f}%</span></div>'
        f'<div class="bm-goal__track" role="progressbar" aria-valuenow="{progress:.0f}" aria-valuemin="0" aria-valuemax="100">'
        f'<div class="bm-goal__fill" style="width:{progress:.1f}%"></div></div>'
        f'<div class="bm-goal__foot"><span>Objetivo {esc(money(target, currency))}</span>'
        f'<span>Faltan {esc(money(gap, currency))}</span></div></div></div></section>'
    )


def section_title(title: str, icon: Optional[str] = None, caption: Optional[str] = None) -> None:
    icon_part = f'<span class="bm-section__icon">{icon_html(icon)}</span>' if icon else ""
    cap = f'<div class="bm-section__caption">{esc(caption)}</div>' if caption else ""
    _md(f'<div class="bm-section"><div class="bm-section__title" role="heading" aria-level="2">{icon_part}'
        f'<span>{esc(title)}</span></div>{cap}</div>')


def stat_cards(stats: List[dict]) -> None:
    """Fila de indicadores. Cada stat: {label, value, icon?, tone?, help?}."""
    cards = []
    for s in stats:
        icon = f'<div class="bm-stat__icon">{icon_html(s.get("icon"))}</div>' if s.get("icon") else ""
        help_text = f'<div class="bm-stat__help">{esc(s.get("help"))}</div>' if s.get("help") else ""
        cards.append(
            f'<div class="bm-stat bm-stat--{_tone(s.get("tone"))}"><div class="bm-stat__top">'
            f'<div class="bm-stat__label">{esc(s.get("label"))}</div>{icon}</div>'
            f'<div class="bm-stat__value">{esc(s.get("value"))}</div>{help_text}</div>'
        )
    _md(f'<div class="bm-stat-grid bm-stat-grid--n{min(len(cards), 6)}">{"".join(cards)}</div>')


def empty_state(title: str, text: str = "", icon: str = "inbox") -> None:
    body = f'<div class="bm-empty__text">{esc(text)}</div>' if text else ""
    _md(f'<div class="bm-empty"><div class="bm-empty__icon">{icon_html(icon)}</div>'
        f'<div class="bm-empty__title">{esc(title)}</div>{body}</div>')


def stake_ladder(profile: List[dict], currency: str) -> None:
    """Escalera visual de unidades (1U → Whale) con barra proporcional al % del bank."""
    top = max((row["pct"] for row in profile), default=1) or 1
    rungs = []
    for row in profile:
        whale = " bm-rung--whale" if row["unit"] == "Whale" else ""
        rungs.append(
            f'<div class="bm-rung{whale}"><span class="bm-rung__unit">{esc(row["unit"])}</span>'
            f'<div class="bm-rung__cash">{esc(money(row["cash"], currency))}</div>'
            f'<div class="bm-rung__meta">{esc(row["label"])} · {row["pct"] * 100:.0f}% · conf ≥ {row["confidence"]:.0f}%</div>'
            f'<div class="bm-rung__bar"><span style="width:{row["pct"] / top * 100:.0f}%"></span></div></div>'
        )
    _md(f'<div class="bm-ladder">{"".join(rungs)}</div>')


def risk_card(level: str, title: str, metrics: List[tuple], alerts: List[dict]) -> None:
    """Semáforo de riesgo (inspirado en la tarjeta de riesgo de SaludIA)."""
    level = level if level in ("success", "warning", "danger") else "warning"
    kv = "".join(f'<div class="bm-risk__kv"><div class="bm-risk__k">{esc(k)}</div>'
                 f'<div class="bm-risk__v">{esc(v)}</div></div>' for k, v in metrics)
    icons = {"danger": "error", "warning": "warning", "success": "check_circle"}
    items = alerts or [{"tone": "success", "text": "La apuesta cumple las reglas del plan."}]
    lis = "".join(f'<li class="is-{_tone(a["tone"])}">{icon_html(icons.get(a["tone"], "info"))}<span>{esc(a["text"])}</span></li>'
                  for a in items)
    _md(f'<div class="bm-risk bm-risk--{level}"><div class="bm-risk__head"><span class="bm-risk__light"></span>'
        f'<span class="bm-risk__title">{esc(title)}</span></div><div class="bm-risk__grid">{kv}</div>'
        f'<ul class="bm-risk__alerts">{lis}</ul></div>')


def timeline(items: List[dict]) -> None:
    """Línea de tiempo vertical. Cada item: {title, meta, amount, tone}."""
    rows = "".join(
        f'<li class="bm-timeline__item bm-timeline__item--{_tone(i.get("tone"))}"><span class="bm-timeline__dot"></span>'
        f'<div><div class="bm-timeline__title">{esc(i.get("title"))}</div><div class="bm-timeline__meta">{esc(i.get("meta"))}</div></div>'
        f'<div class="bm-timeline__amount {"bm-pos" if i.get("tone") == "success" else "bm-neg" if i.get("tone") == "danger" else ""}">'
        f'{esc(i.get("amount"))}</div></li>'
        for i in items
    )
    _md(f'<ul class="bm-timeline">{rows}</ul>')


def sidebar_bank_card(bankroll: float, net: float, progress: float, currency: str) -> None:
    cls = "bm-pos" if net >= 0 else "bm-neg"
    progress = max(0.0, min(progress, 100.0))
    _md(f'<div class="bm-side-card"><div class="bm-side-card__k">Bank actual</div>'
        f'<div class="bm-side-card__v">{esc(money(bankroll, currency))}</div>'
        f'<div class="bm-side-card__row"><span>Neto</span><span class="{cls}">{esc(money(net, currency, signed=True))}</span></div>'
        f'<div class="bm-side-card__row"><span>Meta breakeven</span><span>{progress:.0f}%</span></div>'
        f'<div class="bm-side-card__track"><span style="width:{progress:.1f}%"></span></div></div>')


def footer() -> None:
    _md('<div class="bm-footer">Rushbet BankMaster Pro · Herramienta de gestión de capital. '
        'Apuesta con responsabilidad: el juego implica riesgo de pérdida.</div>')


def flash(message: str, kind: str = "success") -> None:
    """Aviso que sobrevive a ``st.rerun()`` (se muestra con ``show_flash``)."""
    st.session_state["_flash"] = (kind, message)


def show_flash() -> None:
    shown = st.session_state.pop("_flash", None)
    if shown:
        kind, message = shown
        icon = {"success": ":material/check_circle:", "warning": ":material/warning:"}.get(kind, ":material/info:")
        st.toast(message, icon=icon)
