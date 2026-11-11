"""Persistencia transaccional para Rushbet BankMaster Pro.

Producción:
    Define ``DATABASE_URL`` con una URL PostgreSQL. Los datos sobreviven reinicios y
    redespliegues (recomendado para Streamlit Community Cloud).

Desarrollo local:
    Sin ``DATABASE_URL`` se usa SQLite en ``rushbet_bankmaster.db``. La variable
    ``RBM_DB_PATH`` permite indicar otro archivo, principalmente para pruebas.

Cada mutación y su evento de auditoría se escriben en la MISMA transacción: o se guardan
ambos o ninguno. ``pool_pre_ping`` detecta conexiones PostgreSQL vencidas antes de usarlas.
"""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine, make_url

from core.models import STATUSES, BankSettings, compute_net_profit, normalize_status

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "rushbet_bankmaster.db"

BET_FIELDS = (
    "bet_date", "sport", "market", "event_name", "selection", "odds", "stake",
    "confidence", "unit_type", "status", "closing_odds", "notes",
    "recommendation_type", "recommended_value", "recommended_stake", "adjustment_reason",
)
EXPORT_COLUMNS = ("id",) + BET_FIELDS + ("net_profit", "settled_at", "created_at")


def db_path() -> Path:
    """Ruta SQLite local. Se conserva como API pública y para migraciones/pruebas."""
    return Path(os.getenv("RBM_DB_PATH") or _DEFAULT_DB)


def database_url() -> str:
    """URL efectiva sin exponerla en registros ni en la interfaz."""
    explicit_path = os.getenv("RBM_DB_PATH")
    configured = os.getenv("DATABASE_URL")
    if configured and not explicit_path:
        # Algunos proveedores aún entregan postgres://; SQLAlchemy espera postgresql+psycopg://.
        if configured.startswith("postgres://"):
            configured = "postgresql+psycopg://" + configured[len("postgres://"):]
        elif configured.startswith("postgresql://"):
            configured = "postgresql+psycopg://" + configured[len("postgresql://"):]
        return configured
    return f"sqlite:///{db_path().resolve().as_posix()}"


@lru_cache(maxsize=8)
def _engine_for(url: str) -> Engine:
    parsed = make_url(url)
    kwargs: Dict[str, Any] = {"pool_pre_ping": True, "future": True}
    if parsed.get_backend_name() == "sqlite":
        path = Path(parsed.database or str(_DEFAULT_DB))
        path.parent.mkdir(parents=True, exist_ok=True)
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    return create_engine(url, **kwargs)


def get_engine() -> Engine:
    return _engine_for(database_url())


def backend_name() -> str:
    return get_engine().dialect.name


def is_persistent_storage() -> bool:
    """PostgreSQL se considera persistente; SQLite depende del disco del host."""
    return backend_name() == "postgresql"


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _audit(conn: Connection, action: str, entity_type: str, entity_id: Optional[int] = None,
           payload: Optional[Mapping[str, Any]] = None) -> None:
    conn.execute(
        text("""INSERT INTO audit_events (action, entity_type, entity_id, payload)
                VALUES (:action, :entity_type, :entity_id, :payload)"""),
        {"action": action, "entity_type": entity_type, "entity_id": entity_id,
         "payload": json.dumps(dict(payload or {}), ensure_ascii=False, default=_json_default)},
    )


def init_db() -> None:
    """Crea o amplía el esquema sin borrar datos existentes."""
    engine = get_engine()
    serial = "BIGSERIAL PRIMARY KEY" if engine.dialect.name == "postgresql" else "INTEGER PRIMARY KEY AUTOINCREMENT"
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS bets (
                id {serial},
                bet_date TEXT NOT NULL,
                sport TEXT NOT NULL,
                market TEXT NOT NULL,
                event_name TEXT NOT NULL,
                selection TEXT NOT NULL,
                odds DOUBLE PRECISION NOT NULL,
                stake DOUBLE PRECISION NOT NULL,
                confidence DOUBLE PRECISION NOT NULL,
                unit_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT NOT NULL DEFAULT 'pending',
                net_profit DOUBLE PRECISION NOT NULL DEFAULT 0,
                closing_odds DOUBLE PRECISION,
                notes TEXT,
                recommendation_type TEXT,
                recommended_value DOUBLE PRECISION,
                recommended_stake DOUBLE PRECISION,
                adjustment_reason TEXT,
                settled_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id {serial},
                w_date TEXT NOT NULL,
                amount DOUBLE PRECISION NOT NULL,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS audit_events (
                id {serial},
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id BIGINT,
                payload TEXT NOT NULL DEFAULT '{{}}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

    # ``inspect`` funciona igual en SQLite y PostgreSQL. Las columnas son para instalaciones v1.
    columns = {column["name"] for column in inspect(engine).get_columns("bets")}
    with engine.begin() as conn:
        if "closing_odds" not in columns:
            conn.execute(text("ALTER TABLE bets ADD COLUMN closing_odds DOUBLE PRECISION"))
        if "settled_at" not in columns:
            conn.execute(text("ALTER TABLE bets ADD COLUMN settled_at TIMESTAMP"))
        optional_columns = {
            "recommendation_type": "TEXT",
            "recommended_value": "DOUBLE PRECISION",
            "recommended_stake": "DOUBLE PRECISION",
            "adjustment_reason": "TEXT",
        }
        for column, sql_type in optional_columns.items():
            if column not in columns:
                conn.execute(text(f"ALTER TABLE bets ADD COLUMN {column} {sql_type}"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_bets_date ON bets(bet_date)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at)"))
        for key, value in BankSettings().as_dict().items():
            conn.execute(
                text("INSERT INTO settings (key, value) VALUES (:key, :value) ON CONFLICT(key) DO NOTHING"),
                {"key": key, "value": str(value)},
            )
        _migrate_stake_plan(conn)
        _migrate_legacy_status(conn)


def _migrate_stake_plan(conn: Connection) -> None:
    """Migra una instalación con el límite predeterminado antiguo del 10% una sola vez."""
    version = conn.execute(text("SELECT value FROM settings WHERE key = 'stake_plan_version'")).mappings().first()
    if version is not None:
        return
    current = conn.execute(text("SELECT value FROM settings WHERE key = 'max_risk_ratio'")).mappings().first()
    try:
        was_old_default = current is not None and float(current["value"]) == 0.10
    except (TypeError, ValueError):
        was_old_default = False
    if was_old_default:
        conn.execute(text("UPDATE settings SET value = '0.30' WHERE key = 'max_risk_ratio'"))
    conn.execute(text("INSERT INTO settings (key, value) VALUES ('stake_plan_version', '2')"))


def _migrate_legacy_status(conn: Connection) -> None:
    """Unifica status/result de v1 y recalcula el neto sin perder filas."""
    rows = conn.execute(text("SELECT id, odds, stake, status, result, net_profit FROM bets")).mappings().all()
    for row in rows:
        status = normalize_status(row["status"], row["result"])
        net = compute_net_profit(row["odds"], row["stake"], status)
        if status != row["status"] or status != row["result"] or net != row["net_profit"]:
            conn.execute(
                text("UPDATE bets SET status = :status, result = :status, net_profit = :net WHERE id = :id"),
                {"status": status, "net": net, "id": row["id"]},
            )


def health_check() -> Dict[str, Any]:
    """Comprueba escritura y rollback, no solo conectividad de lectura."""
    engine = get_engine()
    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            conn.execute(text("INSERT INTO settings (key, value) VALUES ('__healthcheck__', 'ok') "
                              "ON CONFLICT(key) DO UPDATE SET value = 'ok'"))
            transaction.rollback()
            conn.execute(text("SELECT 1"))
        return {
            "ok": True,
            "backend": engine.dialect.name,
            "persistent": is_persistent_storage(),
            "message": "PostgreSQL persistente conectado" if is_persistent_storage()
            else "SQLite local conectado; el archivo depende del disco del servidor",
        }
    except Exception as exc:
        return {"ok": False, "backend": engine.dialect.name, "persistent": False,
                "message": f"No se pudo escribir en la base de datos ({type(exc).__name__})"}


def _clean_bet(data: Dict[str, Any]) -> Dict[str, Any]:
    clean = {key: data.get(key) for key in BET_FIELDS}
    for key in ("sport", "market", "event_name", "selection"):
        clean[key] = str(clean[key] or "").strip()
        if not clean[key]:
            raise ValueError(f"El campo '{key}' es obligatorio.")
    clean["bet_date"] = str(clean["bet_date"] or "").strip()[:10]
    try:
        date.fromisoformat(clean["bet_date"])
    except ValueError as exc:
        raise ValueError("La fecha debe tener formato AAAA-MM-DD y ser válida.") from exc
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
    clean["recommendation_type"] = str(clean["recommendation_type"] or "confidence")
    clean["recommended_value"] = float(clean["recommended_value"] if clean["recommended_value"] not in (None, "") else clean["confidence"])
    clean["recommended_stake"] = float(clean["recommended_stake"] if clean["recommended_stake"] not in (None, "") else clean["stake"])
    clean["adjustment_reason"] = str(clean["adjustment_reason"] or "").strip()
    return clean


def add_bet(**data: Any) -> int:
    bet = _clean_bet(data)
    net = compute_net_profit(bet["odds"], bet["stake"], bet["status"])
    params = {**bet, "result": bet["status"], "net_profit": net}
    with get_engine().begin() as conn:
        bet_id = conn.execute(text("""
            INSERT INTO bets (bet_date, sport, market, event_name, selection, odds, stake, confidence,
                              unit_type, status, result, net_profit, closing_odds, notes,
                              recommendation_type, recommended_value, recommended_stake, adjustment_reason, settled_at)
            VALUES (:bet_date, :sport, :market, :event_name, :selection, :odds, :stake, :confidence,
                    :unit_type, :status, :result, :net_profit, :closing_odds, :notes,
                    :recommendation_type, :recommended_value, :recommended_stake, :adjustment_reason,
                    CASE WHEN :status = 'pending' THEN NULL ELSE CURRENT_TIMESTAMP END)
            RETURNING id
        """), params).scalar_one()
        _audit(conn, "create", "bet", int(bet_id), {**bet, "net_profit": net})
        return int(bet_id)


def update_bet(bet_id: int, **data: Any) -> None:
    bet = _clean_bet(data)
    net = compute_net_profit(bet["odds"], bet["stake"], bet["status"])
    params = {**bet, "id": int(bet_id), "net_profit": net}
    with get_engine().begin() as conn:
        result = conn.execute(text("""
            UPDATE bets SET bet_date = :bet_date, sport = :sport, market = :market,
                   event_name = :event_name, selection = :selection, odds = :odds, stake = :stake,
                   confidence = :confidence, unit_type = :unit_type, status = :status, result = :status,
                   net_profit = :net_profit, closing_odds = :closing_odds, notes = :notes,
                   recommendation_type = :recommendation_type, recommended_value = :recommended_value,
                   recommended_stake = :recommended_stake, adjustment_reason = :adjustment_reason,
                   settled_at = CASE WHEN :status = 'pending' THEN NULL ELSE COALESCE(settled_at, CURRENT_TIMESTAMP) END
            WHERE id = :id
        """), params)
        if result.rowcount != 1:
            raise ValueError(f"La apuesta #{bet_id} no existe.")
        _audit(conn, "update", "bet", int(bet_id), {**bet, "net_profit": net})


def settle_bet(bet_id: int, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"Estado desconocido: {status}")
    with get_engine().begin() as conn:
        row = conn.execute(text("SELECT odds, stake FROM bets WHERE id = :id"), {"id": int(bet_id)}).mappings().first()
        if row is None:
            raise ValueError(f"La apuesta #{bet_id} no existe.")
        net = compute_net_profit(row["odds"], row["stake"], status)
        conn.execute(text("""
            UPDATE bets SET status = :status, result = :status, net_profit = :net,
                   settled_at = CASE WHEN :status = 'pending' THEN NULL ELSE CURRENT_TIMESTAMP END
            WHERE id = :id
        """), {"status": status, "net": net, "id": int(bet_id)})
        _audit(conn, "settle", "bet", int(bet_id), {"status": status, "net_profit": net})


def delete_bet(bet_id: int) -> None:
    with get_engine().begin() as conn:
        row = conn.execute(text("SELECT * FROM bets WHERE id = :id"), {"id": int(bet_id)}).mappings().first()
        if row is None:
            return
        _audit(conn, "delete", "bet", int(bet_id), dict(row))
        conn.execute(text("DELETE FROM bets WHERE id = :id"), {"id": int(bet_id)})


def get_bets() -> List[Dict[str, Any]]:
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT * FROM bets ORDER BY bet_date DESC, id DESC")).mappings().all()
    return [dict(row) for row in rows]


def get_bet(bet_id: int) -> Optional[Dict[str, Any]]:
    with get_engine().connect() as conn:
        row = conn.execute(text("SELECT * FROM bets WHERE id = :id"), {"id": int(bet_id)}).mappings().first()
    return dict(row) if row else None


def get_audit_events(limit: int = 100) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT * FROM audit_events ORDER BY id DESC LIMIT :limit"), {"limit": limit}).mappings().all()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.get("payload") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["payload"] = {}
        result.append(item)
    return result


def load_settings() -> BankSettings:
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT key, value FROM settings")).mappings().all()
    return BankSettings.from_mapping({row["key"]: row["value"] for row in rows})


def save_settings(settings: BankSettings) -> None:
    values = settings.as_dict()
    with get_engine().begin() as conn:
        for key, value in values.items():
            conn.execute(text("""INSERT INTO settings (key, value) VALUES (:key, :value)
                                  ON CONFLICT(key) DO UPDATE SET value = :value"""),
                         {"key": key, "value": str(value)})
        _audit(conn, "update", "settings", payload=values)


def add_withdrawal(w_date: str, amount: float, note: str = "") -> int:
    w_date = str(w_date or "").strip()[:10]
    try:
        date.fromisoformat(w_date)
    except ValueError as exc:
        raise ValueError("La fecha debe tener formato AAAA-MM-DD y ser válida.") from exc
    amount = float(amount)
    if amount <= 0:
        raise ValueError("El monto del retiro debe ser mayor que cero.")
    note = str(note or "").strip()
    with get_engine().begin() as conn:
        w_id = conn.execute(text("""
            INSERT INTO withdrawals (w_date, amount, note) VALUES (:w_date, :amount, :note)
            RETURNING id
        """), {"w_date": w_date, "amount": amount, "note": note}).scalar_one()
        _audit(conn, "create", "withdrawal", int(w_id), {"w_date": w_date, "amount": amount, "note": note})
        return int(w_id)


def get_withdrawals() -> List[Dict[str, Any]]:
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT * FROM withdrawals ORDER BY w_date DESC, id DESC")).mappings().all()
    return [dict(row) for row in rows]


def delete_withdrawal(withdrawal_id: int) -> None:
    with get_engine().begin() as conn:
        row = conn.execute(text("SELECT * FROM withdrawals WHERE id = :id"), {"id": int(withdrawal_id)}).mappings().first()
        if row is None:
            return
        _audit(conn, "delete", "withdrawal", int(withdrawal_id), dict(row))
        conn.execute(text("DELETE FROM withdrawals WHERE id = :id"), {"id": int(withdrawal_id)})


def export_csv(bets: List[Dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for bet in bets:
        writer.writerow(bet)
    return buffer.getvalue().encode("utf-8-sig")


def import_csv(content: bytes) -> tuple[int, List[str]]:
    text_content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text_content))
    imported, errors = 0, []
    for line_no, row in enumerate(reader, start=2):
        try:
            row["status"] = normalize_status(row.get("status"), row.get("result"))
            add_bet(**{key: row.get(key) for key in BET_FIELDS})
            imported += 1
        except (ValueError, TypeError) as exc:
            errors.append(f"Fila {line_no}: {exc}")
    if imported:
        with get_engine().begin() as conn:
            _audit(conn, "import", "backup", payload={"rows": imported, "errors": len(errors)})
    return imported, errors


def reset_db() -> None:
    """Borra los datos operativos. El historial de auditoría se conserva en PostgreSQL."""
    engine = get_engine()
    if engine.dialect.name == "sqlite":
        engine.dispose()
        path = db_path()
        if path.exists():
            path.unlink()
        init_db()
        return
    with engine.begin() as conn:
        _audit(conn, "reset", "database", payload={"backend": "postgresql"})
        conn.execute(text("DELETE FROM bets"))
        conn.execute(text("DELETE FROM withdrawals"))
        conn.execute(text("DELETE FROM settings"))
    init_db()
