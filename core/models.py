"""Modelos y constantes de dominio compartidos por la base de datos, la analítica y la interfaz."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, Mapping

# Estados de una apuesta. ``pending`` = abierta; el resto son liquidadas.
STATUSES: Dict[str, str] = {
    "pending": "Pendiente",
    "won": "Ganada",
    "half_won": "Medio ganada",
    "void": "Nula",
    "half_lost": "Medio perdida",
    "lost": "Perdida",
}
SETTLED_STATUSES = frozenset(s for s in STATUSES if s != "pending")
WIN_STATUSES = frozenset({"won", "half_won"})
LOSS_STATUSES = frozenset({"lost", "half_lost"})

# Tono visual de cada estado (coincide con las clases .bm-badge--<tono> de style.css).
STATUS_TONES: Dict[str, str] = {
    "pending": "info",
    "won": "success",
    "half_won": "success",
    "void": "neutral",
    "half_lost": "warning",
    "lost": "danger",
}

UNIT_TYPES = ("1U", "2U", "3U", "4U", "Whale")
# Los tres deportes principales aparecen primero. Los catálogos agilizan el registro,
# pero cada selector acepta valores nuevos para preservar mercados personalizados.
SPORTS = ("Fútbol", "Baloncesto", "Tenis", "Béisbol", "Fútbol americano", "eSports", "MMA / Boxeo", "Otro")
SPORT_MARKETS = {
    "Fútbol": ("1X2", "Doble oportunidad", "Total de goles", "Ambos marcan", "Hándicap asiático", "Córners", "Tarjetas"),
    "Baloncesto": ("Ganador", "Hándicap", "Total de puntos", "Total del equipo", "Margen de victoria", "Props de jugador"),
    "Tenis": ("Ganador del partido", "Hándicap de juegos", "Total de juegos", "Ganador del set", "Marcador exacto", "Props de jugador"),
}
MARKET_SELECTIONS = {
    "1X2": ("Local", "Empate", "Visitante"),
    "Doble oportunidad": ("Local o empate", "Local o visitante", "Empate o visitante"),
    "Ambos marcan": ("Sí", "No"),
    "Ganador": ("Local", "Visitante"),
    "Ganador del partido": ("Jugador 1", "Jugador 2"),
    "Ganador del set": ("Jugador 1", "Jugador 2"),
}
DEFAULT_MARKETS = ("Ganador", "Hándicap", "Total", "Props")
STAKING_MODES = {"fijo": "Fijo (sobre bank inicial)", "dinamico": "Dinámico (sobre bank actual)"}


def compute_net_profit(odds: float, stake: float, status: str) -> float:
    """Ganancia neta de una apuesta según su estado (cuota decimal)."""
    odds, stake = float(odds), float(stake)
    if status == "won":
        value = stake * (odds - 1)
    elif status == "half_won":
        value = stake * (odds - 1) / 2
    elif status == "lost":
        value = -stake
    elif status == "half_lost":
        value = -stake / 2
    else:  # pending / void
        value = 0.0
    return round(value, 2)


def normalize_status(status: Any, result: Any = None) -> str:
    """Convierte el par legado (status, result) de v1 a un único estado válido."""
    for candidate in (status, result):
        value = str(candidate or "").strip().lower()
        if value == "open":
            value = "pending"
        if value in STATUSES and value != "pending":
            return value
    return "pending"


@dataclass(frozen=True)
class BankSettings:
    """Parámetros del plan de capital. Todos los montos en COP."""

    base_bankroll: float = 250_000.0
    subscription_cost: float = 120_000.0
    breakeven_target: float = 370_000.0
    max_special_stake: float = 150_000.0
    max_risk_ratio: float = 0.30
    kelly_fraction: float = 0.25
    max_open_exposure: float = 0.30
    protected_reserve: float = 0.0
    profit_target: float = 120_000.0
    stop_loss_ratio: float = 0.20
    staking_mode: str = "fijo"
    currency: str = "COP"
    monthly_expense_goal: float = 0.0

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BankSettings":
        """Crea la configuración desde texto de SQLite, ignorando claves desconocidas o inválidas."""
        defaults = cls()
        values: Dict[str, Any] = {}
        for f in fields(cls):
            raw = data.get(f.name)
            default = getattr(defaults, f.name)
            if raw is None:
                values[f.name] = default
                continue
            try:
                values[f.name] = float(raw) if isinstance(default, float) else str(raw)
            except (TypeError, ValueError):
                values[f.name] = default
        if values["staking_mode"] not in STAKING_MODES:
            values["staking_mode"] = defaults.staking_mode
        return cls(**values)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
