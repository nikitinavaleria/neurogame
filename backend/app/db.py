import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


def ensure_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ingest_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                client_version TEXT,
                events_count INTEGER NOT NULL,
                api_key_hash TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events_raw (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                event_ts TEXT NOT NULL,
                received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                model_version TEXT,
                payload_json TEXT NOT NULL,
                batch_id INTEGER NOT NULL,
                FOREIGN KEY(batch_id) REFERENCES ingest_batches(id)
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_session_ts ON events_raw(session_id, event_ts);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_user_ts ON events_raw(user_id, event_ts);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events_raw(event_type, event_ts);"
        )


def write_batch(db_path: Path, api_key: str, client_version: str, events: list[dict[str, Any]]) -> None:
    api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ingest_batches (client_version, events_count, api_key_hash)
            VALUES (?, ?, ?)
            """,
            (client_version, len(events), api_key_hash),
        )
        batch_id = int(cur.lastrowid)

        rows = []
        for event in events:
            payload = event.get("payload", {})
            if not isinstance(payload, dict):
                payload = {"raw_payload": payload}
            rows.append(
                (
                    event["event_id"],
                    event["event_type"],
                    event["event_ts"],
                    event["user_id"],
                    event["session_id"],
                    event.get("model_version"),
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    batch_id,
                )
            )

        cur.executemany(
            """
            INSERT OR IGNORE INTO events_raw (
                event_id, event_type, event_ts, user_id, session_id, model_version, payload_json, batch_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def read_raw_events(
    db_path: Path,
    limit: int = 1000,
    offset: int = 0,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(5000, int(limit)))
    safe_offset = max(0, int(offset))
    if not db_path.exists():
        return []

    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        cur = conn.cursor()
        rows = cur.execute(
            """
            SELECT event_id, event_type, event_ts, user_id, session_id, model_version, payload_json
            FROM events_raw
            ORDER BY id ASC
            LIMIT ? OFFSET ?
            """,
            (safe_limit, safe_offset),
        ).fetchall()

    records: list[dict[str, Any]] = []
    for event_id, event_type, event_ts, user_id, session_id, model_version, payload_json in rows:
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        records.append(
            {
                "event_id": event_id,
                "event_type": event_type,
                "event_ts": event_ts,
                "user_id": user_id,
                "session_id": session_id,
                "model_version": model_version,
                "payload": payload,
            }
        )
    return records
