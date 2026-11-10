import sqlite3

import pytest

from conftest import make_bet
from core.analytics import (advise_stake, breakdown, build_cumulative_bankroll, get_stake_profile, kelly_fraction,
                            max_drawdown, monthly_summary, stake_for_unit, summarize_bets, unit_for_confidence)
from core.models import BankSettings, compute_net_profit, normalize_status
from ui.components import money


# ------------------------------------------------------------------ modelos
@pytest.mark.parametrize("status,expected", [
    ("won", 11_000), ("half_won", 5_500), ("lost", -10_000), ("half_lost", -5_000), ("void", 0), ("pending", 0)])
def test_net_profit(status, expected):
    assert compute_net_profit(2.1, 10_000, status) == expected


def test_normalize_legacy_status():
    assert normalize_status("open", "pending") == "pending"
    assert normalize_status("open", "won") == "won"  # v1 permitía status abierto con resultado ganado
    assert normalize_status("lost", "pending") == "lost"
    assert normalize_status("basura") == "pending"


def test_settings_from_mapping_ignores_bad_values():
    cfg = BankSettings.from_mapping({"base_bankroll": "300000", "max_risk_ratio": "x", "staking_mode": "raro", "extra": 1})
    assert cfg.base_bankroll == 300_000
    assert cfg.max_risk_ratio == 0.30
    assert cfg.staking_mode == "fijo"


# ------------------------------------------------------------------ base de datos
def test_crud_and_settle(temp_db):
    bet_id = temp_db.add_bet(**make_bet())
    assert temp_db.get_bet(bet_id)["net_profit"] == 0
    temp_db.settle_bet(bet_id, "won")
    row = temp_db.get_bet(bet_id)
    assert (row["status"], row["result"], row["net_profit"]) == ("won", "won", 10_000)
    assert row["settled_at"]
    temp_db.update_bet(bet_id, **make_bet(status="lost", stake=5_000))
    assert temp_db.get_bet(bet_id)["net_profit"] == -5_000
    temp_db.delete_bet(bet_id)
    assert temp_db.get_bets() == []
    assert [event["action"] for event in temp_db.get_audit_events()] == ["delete", "update", "settle", "create"]


def test_write_and_audit_are_atomic(temp_db, monkeypatch):
    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(temp_db, "_audit", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        temp_db.add_bet(**make_bet())
    assert temp_db.get_bets() == []


def test_database_health_check_verifies_writes(temp_db):
    health = temp_db.health_check()
    assert health["ok"] is True
    assert health["backend"] == "sqlite"
    assert health["persistent"] is False
    # La escritura de prueba se revierte y no contamina la configuración.
    with temp_db.get_engine().connect() as conn:
        assert conn.exec_driver_sql("SELECT COUNT(*) FROM settings WHERE key='__healthcheck__'").scalar_one() == 0


@pytest.mark.parametrize("bad", [dict(odds=1.0), dict(stake=0), dict(event_name="  "), dict(confidence=120),
                                 dict(bet_date="ayer"), dict(closing_odds=0.9)])
def test_validation(temp_db, bad):
    with pytest.raises(ValueError):
        temp_db.add_bet(**make_bet(**bad))


def test_settings_roundtrip(temp_db):
    temp_db.save_settings(BankSettings(base_bankroll=500_000, staking_mode="dinamico"))
    cfg = temp_db.load_settings()
    assert cfg.base_bankroll == 500_000 and cfg.staking_mode == "dinamico"


def test_old_default_risk_limit_migrates_once(temp_db):
    with sqlite3.connect(temp_db.db_path()) as conn:
        conn.execute("DELETE FROM settings WHERE key = 'stake_plan_version'")
        conn.execute("UPDATE settings SET value = '0.10' WHERE key = 'max_risk_ratio'")
    temp_db.init_db()
    assert temp_db.load_settings().max_risk_ratio == 0.30
    # Una preferencia posterior del usuario no se vuelve a sobrescribir.
    with sqlite3.connect(temp_db.db_path()) as conn:
        conn.execute("UPDATE settings SET value = '0.12' WHERE key = 'max_risk_ratio'")
    temp_db.init_db()
    assert temp_db.load_settings().max_risk_ratio == 0.12


def test_legacy_rows_are_migrated(temp_db):
    with sqlite3.connect(temp_db.db_path()) as conn:
        conn.execute("INSERT INTO bets (bet_date, sport, market, event_name, selection, odds, stake, confidence, unit_type,"
                     " status, result, net_profit) VALUES ('2026-10-01','F','1X2','X','Y',3.0,1000,80,'1U','open','won',0)")
    temp_db.init_db()
    row = temp_db.get_bets()[0]
    assert row["status"] == "won" and row["net_profit"] == 2000


def test_csv_roundtrip(temp_db):
    temp_db.add_bet(**make_bet(status="won", closing_odds=1.9))
    temp_db.add_bet(**make_bet(event_name="C vs D", status="lost"))
    data = temp_db.export_csv(temp_db.get_bets())
    temp_db.reset_db()
    imported, errors = temp_db.import_csv(data)
    assert (imported, errors) == (2, [])
    assert sum(b["net_profit"] for b in temp_db.get_bets()) == 0


def test_import_reports_bad_rows(temp_db):
    content = "bet_date,sport,market,event_name,selection,odds,stake,confidence,unit_type,status\n" \
              "2026-11-01,F,1X2,A,B,0.5,100,80,1U,won\n".encode()
    imported, errors = temp_db.import_csv(content)
    assert imported == 0 and "Fila 2" in errors[0]


# ------------------------------------------------------------------ analítica
def _bets():
    rows = [
        make_bet(id=1, bet_date="2026-10-01", status="won", odds=2.0, stake=10_000, sport="Fútbol"),
        make_bet(id=2, bet_date="2026-10-02", status="lost", odds=1.8, stake=20_000, sport="Tenis"),
        make_bet(id=3, bet_date="2026-11-03", status="void", odds=1.5, stake=5_000, sport="Fútbol"),
        make_bet(id=4, bet_date="2026-11-04", status="pending", odds=2.5, stake=5_000, sport="Fútbol"),
    ]
    for r in rows:
        r["net_profit"] = compute_net_profit(r["odds"], r["stake"], r["status"])
    return rows


def test_summary_metrics():
    m = summarize_bets(_bets(), BankSettings())
    assert m["net_profit"] == -10_000
    assert m["total_staked"] == 35_000
    assert m["yield"] == round(-10_000 / 35_000 * 100, 2)
    assert m["win_rate"] == 50.0  # la nula no cuenta
    assert m["current_bankroll"] == 240_000
    assert m["pending_bets"] == 1 and m["open_exposure"] == 5_000
    assert m["breakeven_gap"] == 130_000
    assert m["max_drawdown"] == 20_000
    assert m["streaks"]["current"] == "1L"


def test_empty_summary():
    m = summarize_bets([], BankSettings())
    assert m["total_bets"] == 0 and m["current_bankroll"] == 250_000 and m["clv_avg"] is None


def test_curve_and_drawdown():
    curve = build_cumulative_bankroll(_bets(), BankSettings())
    assert [p["bankroll"] for p in curve] == [250_000, 260_000, 240_000, 240_000]
    assert max_drawdown([100, 120, 90, 130, 117])["amount"] == 30


def test_breakdowns():
    by_sport = breakdown(_bets(), "sport")
    assert set(by_sport["sport"]) == {"Fútbol", "Tenis"}
    assert by_sport.iloc[0]["neto"] == 10_000
    assert set(breakdown(_bets(), "odds_band")["odds_band"]) == {"1.51–2.00", "1.01–1.50"}
    assert list(monthly_summary(_bets())["mes"]) == ["2026-10", "2026-11"]


def test_kelly_and_units():
    assert kelly_fraction(2.0, 0.5) == 0
    assert kelly_fraction(2.0, 0.6) == pytest.approx(0.2)
    expected = {
        50: "—", 69: "—", 70: "1U", 74: "1U", 75: "2U", 79: "2U",
        80: "3U", 84: "3U", 85: "4U", 89: "4U", 90: "Whale", 95: "Whale", 100: "Whale",
    }
    assert {confidence: unit_for_confidence(confidence) for confidence in expected} == expected


def test_agreed_stake_percentages_are_exact():
    cfg = BankSettings()
    bank = 253_217.35
    assert stake_for_unit("1U", bank, cfg) == 12_660.87
    assert stake_for_unit("2U", bank, cfg) == 25_321.74
    assert stake_for_unit("3U", bank, cfg) == 50_643.47
    assert stake_for_unit("4U", bank, cfg) == 63_304.34
    assert stake_for_unit("Whale", bank, cfg) == 75_965.21
    assert stake_for_unit("desconocida", bank, cfg) == 0
    assert money(10_128.69) == "$10.128,69 COP"
    assert money(5_000) == "$5.000 COP"


def test_stake_profile_caps_whale():
    profile = {r["unit"]: r for r in get_stake_profile(2_000_000, BankSettings())}
    assert profile["1U"]["cash"] == 100_000
    assert profile["Whale"]["cash"] == 150_000  # tope absoluto


def test_advisor_flags_risk():
    ok = advise_stake(2.0, 80, 50_000, [], BankSettings(), selected_unit="3U")
    assert ok.level == "success" and ok.edge == 30.0
    bad = advise_stake(1.5, 60, 200_000, [], BankSettings())
    assert bad.level == "danger"
    assert any("Sin ventaja" in a["text"] for a in bad.alerts)


def test_advisor_flags_manual_percentage_or_unit_mismatch():
    stake_mismatch = advise_stake(2.0, 80, 49_999, [], BankSettings(), selected_unit="3U")
    assert any("exactamente 20%" in alert["text"] for alert in stake_mismatch.alerts)
    unit_mismatch = advise_stake(2.0, 80, 25_000, [], BankSettings(), selected_unit="2U")
    assert any("recomienda 3U" in alert["text"] for alert in unit_mismatch.alerts)


def test_dynamic_staking_uses_current_bank():
    cfg = BankSettings(staking_mode="dinamico")
    adv = advise_stake(2.0, 80, 48_000, _bets(), cfg)  # bank actual 240k -> 3U = 48.000
    assert adv.unit_stake == 48_000
