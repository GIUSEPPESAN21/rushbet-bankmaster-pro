"""Acceso a datos para las vistas: una sola lectura de apuestas y configuración por ejecución."""

from __future__ import annotations

from typing import List, Tuple

from core import database as db
from core.models import BankSettings


def load() -> Tuple[List[dict], BankSettings]:
    return db.get_bets(), db.load_settings()
