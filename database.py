import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

DB_PATH = Path(__file__).with_name("rushbet_bankmaster.db")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "base_bankroll": 250000.0,
    "subscription_cost": 120000.0,
    "breakeven_target": 370000.0,
    "max_special_stake": 150000.0,
    "max_risk_ratio": 0.10,
}


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bet_date TEXT NOT NULL,
            sport TEXT NOT NULL,
            market TEXT NOT NULL,
            event_name TEXT NOT NULL,
            selection TEXT NOT NULL,
            odds REAL NOT NULL,
            stake REAL NOT NULL,
            confidence REAL NOT NULL,
            unit_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            result TEXT NOT NULL DEFAULT 'pending',
            net_profit REAL NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.commit()

    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value)),
        )
    conn.commit()
    conn.close()


def _compute_net_profit(odds: float, stake: float, result: str) -> float:
    if result == "won":
        return round(stake * (odds - 1), 2)
    if result == "lost":
        return round(-stake, 2)
    if result == "void":
        return 0.0
    return 0.0


def add_bet(
    bet_date: str,
    sport: str,
    market: str,
    event_name: str,
    selection: str,
    odds: float,
    stake: float,
    confidence: float,
    unit_type: str,
    status: str = "open",
    result: str = "pending",
    notes: str = "",
) -> int:
    conn = get_connection()
    net_profit = _compute_net_profit(odds, stake, result if status in {"won", "lost", "void"} else "pending")
    cursor = conn.execute(
        """
        INSERT INTO bets (
            bet_date, sport, market, event_name, selection,
            odds, stake, confidence, unit_type, status, result,
            net_profit, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            bet_date,
            sport,
            market,
            event_name,
            selection,
            float(odds),
            float(stake),
            float(confidence),
            unit_type,
            status,
            result,
            float(net_profit),
            notes,
        ),
    )
    conn.commit()
    bet_id = cursor.lastrowid
    conn.close()
    return int(bet_id)


def get_bets() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM bets ORDER BY bet_date DESC, id DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_bet(bet_id: int) -> None:
    conn = get_connection()
    conn.execute("DELETE FROM bets WHERE id = ?", (bet_id,))
    conn.commit()
    conn.close()


def update_bet(
    bet_id: int,
    bet_date: str,
    sport: str,
    market: str,
    event_name: str,
    selection: str,
    odds: float,
    stake: float,
    confidence: float,
    unit_type: str,
    status: str,
    result: str,
    notes: str,
) -> None:
    conn = get_connection()
    net_profit = _compute_net_profit(odds, stake, result if status in {"won", "lost", "void"} else "pending")
    conn.execute(
        """
        UPDATE bets
        SET bet_date = ?, sport = ?, market = ?, event_name = ?, selection = ?,
            odds = ?, stake = ?, confidence = ?, unit_type = ?, status = ?,
            result = ?, net_profit = ?, notes = ?
        WHERE id = ?
        """,
        (
            bet_date,
            sport,
            market,
            event_name,
            selection,
            float(odds),
            float(stake),
            float(confidence),
            unit_type,
            status,
            result,
            float(net_profit),
            notes,
            bet_id,
        ),
    )
    conn.commit()
    conn.close()


def save_setting(key: str, value: Any) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def get_setting(key: str, default: Optional[Any] = None) -> Any:
    conn = get_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row is None:
        return default
    value = row["value"]
    if isinstance(default, bool):
        return value.lower() == "true"
    if isinstance(default, int):
        return int(float(value))
    if isinstance(default, float):
        return float(value)
    return value


def get_all_settings() -> Dict[str, Any]:
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    data = {}
    for row in rows:
        data[row["key"]] = row["value"]
    return data


def reset_db() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    init_db()
