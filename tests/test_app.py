"""Pruebas de humo: la app y cada página se ejecutan sin excepciones (vacías y con datos)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from conftest import make_bet

ROOT = Path(__file__).resolve().parent.parent
VIEWS = ["dashboard", "new_bet", "history", "analytics", "ai", "settings"]


def _view(module: str) -> AppTest:
    script = (
        "import sys\n"
        f"sys.path.insert(0, r'{ROOT}')\n"
        "from core import database as db\n"
        "db.init_db()\n"
        "from ui import components as ui\n"
        "ui.load_theme()\n"
        f"from ui.views import {module}\n"
        f"{module}.render()\n"
    )
    at = AppTest.from_string(script, default_timeout=30)
    at.run()
    return at


def _seed(db):
    db.add_bet(**make_bet(status="won", closing_odds=1.9))
    db.add_bet(**make_bet(event_name="<script>x</script>", status="lost", sport="Tenis", bet_date="2026-10-15"))
    db.add_bet(**make_bet(status="pending"))


def test_main_app_runs(temp_db):
    _seed(temp_db)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.run()
    assert not at.exception, at.exception


@pytest.mark.parametrize("with_data", [False, True])
@pytest.mark.parametrize("module", VIEWS)
def test_views_render(temp_db, monkeypatch, module, with_data):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    if with_data:
        _seed(temp_db)
    at = _view(module)
    assert not at.exception, at.exception


def test_user_text_is_escaped(temp_db):
    _seed(temp_db)
    at = _view("dashboard")
    html = " ".join(m.value for m in at.markdown)
    assert "<script>x</script>" not in html and "&lt;script&gt;" in html


def test_settle_from_history(temp_db):
    temp_db.add_bet(**make_bet())
    bet_id = temp_db.get_bets()[0]["id"]
    at = _view("history")
    at.button(key=f"settle_won_{bet_id}").click().run()
    assert not at.exception
    assert temp_db.get_bet(bet_id)["status"] == "won"


def test_new_bet_saves(temp_db):
    at = _view("new_bet")
    at.text_input(key="qb_event").input("Real vs Barça")
    at.text_input(key="qb_selection").input("Local")
    at.run()
    next(b for b in at.button if b.label == "Guardar apuesta").click().run()
    assert not at.exception
    bets = temp_db.get_bets()
    assert len(bets) == 1 and bets[0]["event_name"] == "Real vs Barça"


def test_ai_local_report(temp_db, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _seed(temp_db)
    at = _view("ai")
    next(b for b in at.button if b.label == "Generar análisis").click().run()
    assert not at.exception
    assert any("Diagnóstico local" in m.value for m in at.markdown)
