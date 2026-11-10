"""Persistencia SQLite de apuestas y configuración.

Cambios frente a v1:
- Un único campo de estado (``status``); ``result`` se conserva por compatibilidad y se
  sincroniza automáticamente. Las filas antiguas (status/result separados) se migran al iniciar.
- Conexiones con ``with`` (se cierran aunque falle la consulta) y validación de entradas.
- Ruta configurable con la variable de entorno ``RBM_DB_PATH`` (útil para pruebas y despliegues).
- Exportación / importación CSV para respaldar el historial (en Streamlit Cloud el disco es efímero).
"""

from __future__ import annotations

import csv
import io
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from core.models import STATUSES, BankSettings, compute_net_profit, normalize_status

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "rushbet_bankmaster.db"

BET_FIELDS = (
    "bet_date", "sport", "market", "event_name", "selection", "odds", "stake",
    "confidence", "unit_type", "status", "closing_odds", "notes",
)


def db_path() -> Path:
    return Path(os.getenv("RBM_DB_PATH") or _DEFAULT_DB)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
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
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT NOT NULL DEFAULT 'pending',
                net_profit REAL NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(bets)")}
        if "closing_odds" not in columns:
            conn.execute("ALTER TABLE bets ADD COLUMN closing_odds REAL")
        if "settled_at" not in columns:
            conn.execute("ALTER TABLE bets ADD COLUMN settled_at TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bets_date ON bets(bet_date)")
        for key, value in BankSettings().as_dict().items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        _migrate_stake_plan(conn)
        _migrate_legacy_status(conn)


def _migrate_stake_plan(conn: sqlite3.Connection) -> None:
    """Actualiza una instalación con el antiguo límite predeterminado del 10%.

    El marcador evita sobrescribir cambios posteriores del usuario. Si el límite ya era
    distinto del antiguo valor predeterminado, se conserva.
    """
    version = conn.execute("SELECT value FROM settings WHERE key = 'stake_plan_version'").fetchone()
    if version is not None:
        return
    current = conn.execute("SELECT value FROM settings WHERE key = 'max_risk_ratio'").fetchone()
    try:
        was_old_default = current is not None and float(current["value"]) == 0.10
    except (TypeError, ValueError):
        was_old_default = False
    if was_old_default:
        conn.execute("UPDATE settings SET value = '0.30' WHERE key = 'max_risk_ratio'")
    conn.execute("INSERT INTO settings (key, value) VALUES ('stake_plan_version', '2')")


def _migrate_legacy_status(conn: sqlite3.Connection) -> None:
    """v1 guardaba 'open' y permitía status/result contradictorios: se unifican y se recalcula el neto."""
    rows = conn.execute("SELECT id, odds, stake, status, result, net_profit FROM bets").fetchall()
    for row in rows:
        status = normalize_status(row["status"], row["result"])
        net = compute_net_profit(row["odds"], row["stake"], status)
        if status != row["status"] or status != row["result"] or net != row["net_profit"]:
            conn.execute(
                "UPDATE bets SET status = ?, result = ?, net_profit = ? WHERE id = ?",
                (status, status, net, row["id"]),
            )


def _clean_bet(data: Dict[str, Any]) -> Dict[str, Any]:
    """Valida y normaliza una apuesta. Lanza ValueError con un mensaje legible."""
    clean = {k: data.get(k) for k in BET_FIELDS}
    for key in ("sport", "market", "event_name", "selection"):
        clean[key] = str(clean[key] or "").strip()
        if not clean[key]:
            raise ValueError(f"El campo '{key}' es obligatorio.")
    clean["bet_date"] = str(clean["bet_date"] or "").strip()[:10]
    if len(clean["bet_date"]) != 10:
        raise ValueError("La fecha debe tener formato AAAA-MM-DD.")
    clean["odds"] = float(clean["odds"])
    clean["stake"] = float(clean["stake"])
    clean["confidence"] = float(clean["confidence"] if clean["confidence"] is not None else 0)
    if clean["odds"] <= 1.0:
        raise ValueError("La cuota decimal debe ser mayor que 1.00.")
    if clean["stake"] <= 0:
        raise ValueError("El stake debe ser mayor que cero.")
    if not 0 <= clean["confidence"] <= 100:
        raise ValueError("La confianza debe estar entre 0 y 100.")
    clean["status"] = normalize_status(clean["status"])
    closing = clean["closing_odds"]
    clean["closing_odds"] = float(closing) if closing not in (None, "", 0, 0.0) else None
    if clean["closing_odds"] is not None and clean["closing_odds"] <= 1.0:
        raise ValueError("La cuota de cierre debe ser mayor que 1.00.")
    clean["unit_type"] = str(clean["unit_type"] or "1U")
    clean["notes"] = str(clean["notes"] or "").strip()
    return clean


def add_bet(**data: Any) -> int:
    bet = _clean_bet(data)
    net = compute_net_profit(bet["odds"], bet["stake"], bet["status"])
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO bets (bet_date, sport, market, event_name, selection, odds, stake, confidence,
                              unit_type, status, result, net_profit, closing_odds, notes, settled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    CASE WHEN ? = 'pending' THEN NULL ELSE CURRENT_TIMESTAMP END)
            """,
            (bet["bet_date"], bet["sport"], bet["market"], bet["event_name"], bet["selection"],
             bet["odds"], bet["stake"], bet["confidence"], bet["unit_type"], bet["status"],
             bet["status"], net, bet["closing_odds"], bet["notes"], bet["status"]),
        )
        return int(cursor.lastrowid)


def update_bet(bet_id: int, **data: Any) -> None:
    bet = _clean_bet(data)
    net = compute_net_profit(bet["odds"], bet["stake"], bet["status"])
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE bets SET bet_date = ?, sport = ?, market = ?, event_name = ?, selection = ?, odds = ?,
                   stake = ?, confidence = ?, unit_type = ?, status = ?, result = ?, net_profit = ?,
                   closing_odds = ?, notes = ?,
                   settled_at = CASE WHEN ? = 'pending' THEN NULL ELSE COALESCE(settled_at, CURRENT_TIMESTAMP) END
            WHERE id = ?
            """,
            (bet["bet_date"], bet["sport"], bet["market"], bet["event_name"], bet["selection"],
             bet["odds"], bet["stake"], bet["confidence"], bet["unit_type"], bet["status"],
             bet["status"], net, bet["closing_odds"], bet["notes"], bet["status"], int(bet_id)),
        )


def settle_bet(bet_id: int, status: str) -> None:
    """Liquida (o reabre) una apuesta y recalcula su neto."""
    if status not in STATUSES:
        raise ValueError(f"Estado desconocido: {status}")
    with get_connection() as conn:
        row = conn.execute("SELECT odds, stake FROM bets WHERE id = ?", (int(bet_id),)).fetchone()
        if row is None:
            raise ValueError(f"La apuesta #{bet_id} no existe.")
        net = compute_net_profit(row["odds"], row["stake"], status)
        conn.execute(
            """UPDATE bets SET status = ?, result = ?, net_profit = ?,
                   settled_at = CASE WHEN ? = 'pending' THEN NULL ELSE CURRENT_TIMESTAMP END
               WHERE id = ?""",
            (status, status, net, status, int(bet_id)),
        )


def delete_bet(bet_id: int) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM bets WHERE id = ?", (int(bet_id),))


def get_bets() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM bets ORDER BY bet_date DESC, id DESC").fetchall()
    return [dict(row) for row in rows]


def get_bet(bet_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM bets WHERE id = ?", (int(bet_id),)).fetchone()
    return dict(row) if row else None


# --------------------------------------------------------------------------- configuración

def load_settings() -> BankSettings:
    with get_connection() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return BankSettings.from_mapping({row["key"]: row["value"] for row in rows})


def save_settings(settings: BankSettings) -> None:
    with get_connection() as conn:
        for key, value in settings.as_dict().items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )


# --------------------------------------------------------------------------- respaldo CSV

EXPORT_COLUMNS = ("id",) + BET_FIELDS + ("net_profit", "settled_at", "created_at")


def export_csv(bets: List[Dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for bet in bets:
        writer.writerow(bet)
    return buffer.getvalue().encode("utf-8-sig")


def import_csv(content: bytes) -> tuple[int, List[str]]:
    """Importa apuestas desde un CSV exportado. Devuelve (importadas, errores por fila)."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    imported, errors = 0, []
    for line_no, row in enumerate(reader, start=2):
        try:
            row["status"] = normalize_status(row.get("status"), row.get("result"))
            add_bet(**{k: row.get(k) for k in BET_FIELDS})
            imported += 1
        except (ValueError, TypeError) as exc:
            errors.append(f"Fila {line_no}: {exc}")
    return imported, errors


def reset_db() -> None:
    path = db_path()
    if path.exists():
        path.unlink()
    init_db()
