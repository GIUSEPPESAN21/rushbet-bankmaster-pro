"""Gráficos Plotly con la identidad visual de la app (fondos transparentes: heredan el tema claro/oscuro)."""

from __future__ import annotations

from typing import List

import pandas as pd
import plotly.graph_objects as go

GAIN = "#00A86B"
LOSS = "#E5484D"
NAVY = "#1F4E8C"
GOLD = "#F5B700"
MUTED = "#8A97AD"


def _style(fig: go.Figure, height: int = 360, title: str = "") -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0.01, font=dict(size=15)),
        height=height,
        margin=dict(l=10, r=10, t=48 if title else 16, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, sans-serif", size=12),
        hoverlabel=dict(font=dict(family="Inter, Segoe UI, sans-serif")),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        separators=",.",
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="rgba(138,151,173,0.18)", zeroline=False)
    return fig


def bankroll_curve(points: List[dict], base: float, target: float) -> go.Figure:
    df = pd.DataFrame(points)
    peak = df["bankroll"].cummax()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["n"], y=peak, mode="lines", line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(
        x=df["n"], y=df["bankroll"], mode="lines+markers", name="Bank",
        line=dict(color=GAIN, width=3, shape="spline", smoothing=0.6),
        marker=dict(size=7, color=[GAIN if v >= 0 else LOSS for v in df["net"]], line=dict(width=1.5, color="#FFFFFF")),
        fill="tonexty", fillcolor="rgba(229,72,77,0.10)",
        customdata=df[["label", "net"]].fillna(""),
        hovertemplate="<b>%{customdata[0]}</b><br>Bank: $%{y:,.0f}<br>Neto: %{customdata[1]:,.0f}<extra></extra>",
    ))
    fig.add_hline(y=base, line=dict(color=MUTED, dash="dot"), annotation_text="Bank inicial", annotation_position="bottom right")
    fig.add_hline(y=target, line=dict(color=GOLD, dash="dash"), annotation_text="Meta breakeven", annotation_position="top right")
    fig.update_xaxes(title="Apuesta #")
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    return _style(fig, 380, "Evolución del bankroll (zona roja = drawdown)")


def profit_bars(df: pd.DataFrame, category: str, title: str) -> go.Figure:
    data = df.sort_values("neto")
    fig = go.Figure(go.Bar(
        x=data["neto"], y=data[category].astype(str), orientation="h",
        marker=dict(color=[GAIN if v >= 0 else LOSS for v in data["neto"]], cornerradius=6),
        customdata=data[["apuestas", "yield"]],
        hovertemplate="<b>%{y}</b><br>Neto: $%{x:,.0f}<br>Apuestas: %{customdata[0]}<br>Yield: %{customdata[1]:.2f}%<extra></extra>",
    ))
    fig.update_xaxes(tickprefix="$", tickformat=",.0f")
    return _style(fig, max(260, 60 + 42 * len(data)), title)


def results_donut(wins: int, losses: int, voids: int, pending: int) -> go.Figure:
    labels, values, colors = [], [], []
    for label, value, color in (("Ganadas", wins, GAIN), ("Perdidas", losses, LOSS), ("Nulas", voids, MUTED), ("Pendientes", pending, NAVY)):
        if value:
            labels.append(label), values.append(value), colors.append(color)
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.62, marker=dict(colors=colors),
                           textinfo="value", sort=False, hovertemplate="%{label}: %{value} (%{percent})<extra></extra>"))
    total = wins + losses
    rate = wins / total * 100 if total else 0
    fig.add_annotation(text=f"<b>{rate:.0f}%</b><br><span style='font-size:11px'>win rate</span>", showarrow=False, font=dict(size=20))
    return _style(fig, 300, "Resultados")


def monthly_bars(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=df["mes"], y=df["neto"], marker=dict(color=[GAIN if v >= 0 else LOSS for v in df["neto"]], cornerradius=6),
        customdata=df[["apuestas", "yield"]],
        hovertemplate="<b>%{x}</b><br>Neto: $%{y:,.0f}<br>Apuestas: %{customdata[0]}<br>Yield: %{customdata[1]:.2f}%<extra></extra>",
    ))
    fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    return _style(fig, 320, "Beneficio neto por mes")


def kelly_gauge(edge: float) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=edge, number=dict(suffix=" pp", valueformat="+.1f"),
        gauge=dict(axis=dict(range=[-20, 20]), bar=dict(color=GAIN if edge > 0 else LOSS, thickness=0.3),
                   steps=[dict(range=[-20, 0], color="rgba(229,72,77,0.15)"), dict(range=[0, 20], color="rgba(0,168,107,0.15)")],
                   threshold=dict(line=dict(color=GOLD, width=3), value=0)),
        title=dict(text="Ventaja estimada vs. cuota"),
    ))
    return _style(fig, 240)
