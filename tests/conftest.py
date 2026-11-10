import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("RBM_DB_PATH", str(tmp_path / "test.db"))
    from core import database

    database.init_db()
    return database


def make_bet(**overrides):
    bet = dict(bet_date="2026-11-01", sport="Fútbol", market="1X2", event_name="A vs B", selection="Local",
               odds=2.0, stake=10_000, confidence=80, unit_type="2U", status="pending", closing_odds=None, notes="")
    bet.update(overrides)
    return bet
