import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_ts_seconds(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str) or not value.strip():
        return int(datetime.now(tz=timezone.utc).timestamp())
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return int(datetime.now(tz=timezone.utc).timestamp())
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def to_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _infer_mode(model_version: Any, payload: dict[str, Any]) -> str:
    if isinstance(payload.get("mode"), str):
        return payload["mode"]
    if isinstance(model_version, str) and "ppo" in model_version.lower():
        return "ppo"
    return "baseline"


def export_bridge(
    db_path: Path,
    events_out: Path,
    adaptations_out: Path,
    sessions_out: Path | None,
) -> tuple[int, int, int]:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite db not found: {db_path}")

    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT event_id, event_type, event_ts, user_id, session_id, model_version, payload_json
            FROM events_raw
            ORDER BY event_ts ASC, id ASC
            """
        )
        rows = cur.fetchall()

    event_records: list[dict[str, Any]] = []
    adaptation_records: list[dict[str, Any]] = []
    session_records: list[dict[str, Any]] = []

    for event_id, event_type, event_ts, user_id, session_id, model_version, payload_json in rows:
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except json.JSONDecodeError:
            payload = {}
        payload = _as_dict(payload)
        ts = parse_ts_seconds(event_ts)

        if event_type == "task_result":
            nested_payload = _as_dict(payload.get("payload"))
            rec = {
                "timestamp": ts,
                "session_id": payload.get("session_id", session_id),
                "user_id": payload.get("user_id", user_id),
                "batch_index": payload.get("batch_index"),
                "batch_task_index": payload.get("batch_task_index"),
                "task_id": payload.get("task_id"),
                "difficulty": _as_dict(payload.get("difficulty")),
                "global_difficulty": _as_dict(payload.get("global_difficulty")),
                "level": payload.get("level"),
                "adapt_state": payload.get("adapt_state"),
                "adapt_action": payload.get("adapt_action"),
                "adapt_reward": payload.get("adapt_reward"),
                "mode": _infer_mode(model_version, payload),
                "payload": nested_payload,
                "response": payload.get("response"),
                "correct": int(payload.get("correct", 0)),
                "reaction_time": payload.get("reaction_time"),
                "deadline_met": int(payload.get("deadline_met", 0)),
                "source_event_id": event_id,
            }
            event_records.append(rec)
            continue

        if event_type == "adaptation_step":
            rec = {
                "step": int(payload.get("step", 0)),
                "user_id": payload.get("user_id", user_id),
                "session_id": payload.get("session_id", session_id),
                "batch_index": payload.get("batch_index"),
                "batch_tasks_completed": payload.get("batch_tasks_completed"),
                "state": payload.get("state", []),
                "action_id": int(payload.get("action_id", 0)),
                "delta_level": int(payload.get("delta_level", 0)),
                "delta_tempo": int(payload.get("delta_tempo", 0)),
                "reward": float(payload.get("reward", 0.0)),
                "level": int(payload.get("level", 1)),
                "tempo_offset": int(payload.get("tempo_offset", 0)),
                "mode": _infer_mode(model_version, payload),
                "action_space": payload.get("action_space", "tempo3"),
                "source_event_id": event_id,
            }
            adaptation_records.append(rec)
            continue

        if sessions_out is not None and event_type in ("session_end", "session_end_partial"):
            is_partial = int(payload.get("is_partial", 1 if event_type == "session_end_partial" else 0))
            rec = {
                "session_id": payload.get("session_id", session_id),
                "user_id": payload.get("user_id", user_id),
                "total_tasks": int(payload.get("total_tasks", 0)),
                "accuracy_total": float(payload.get("accuracy_total", 0.0)),
                "mean_rt": float(payload.get("mean_rt", 0.0)),
                "rt_variance": float(payload.get("rt_variance", 0.0)),
                "switch_cost": float(payload.get("switch_cost", 0.0)),
                "fatigue_trend": float(payload.get("fatigue_trend", 0.0)),
                "overload_events": int(payload.get("overload_events", 0)),
                "max_level": payload.get("max_level"),
                "last_level": payload.get("last_level"),
                "planets_visited": payload.get("planets_visited"),
                "mode": _infer_mode(model_version, payload),
                "is_partial": is_partial,
                "exit_reason": payload.get("exit_reason"),
                "timestamp": ts,
                "source_event_id": event_id,
            }
            session_records.append(rec)

    to_jsonl(events_out, event_records)
    to_jsonl(adaptations_out, adaptation_records)
    if sessions_out is not None:
        to_jsonl(sessions_out, session_records)
    return len(event_records), len(adaptation_records), len(session_records)


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    default_db = project_root / "backend" / "data" / "events.db"
    default_events = project_root / "data" / "events.jsonl"
    default_adaptations = project_root / "data" / "adaptations.jsonl"
    default_sessions = project_root / "data" / "sessions.jsonl"

    parser = argparse.ArgumentParser(
        description="Export backend SQLite events into current training/analytics JSONL files"
    )
    parser.add_argument("--db", default=str(default_db), help="Path to backend SQLite db")
    parser.add_argument("--events-out", default=str(default_events), help="Output path for task events")
    parser.add_argument(
        "--adaptations-out",
        default=str(default_adaptations),
        help="Output path for adaptation events",
    )
    parser.add_argument(
        "--sessions-out",
        default=str(default_sessions),
        help="Output path for session summaries",
    )
    args = parser.parse_args()

    events_n, adaptations_n, sessions_n = export_bridge(
        db_path=Path(args.db),
        events_out=Path(args.events_out),
        adaptations_out=Path(args.adaptations_out),
        sessions_out=Path(args.sessions_out) if args.sessions_out else None,
    )
    print(
        f"Export complete: events={events_n}, adaptations={adaptations_n}, sessions={sessions_n}"
    )


if __name__ == "__main__":
    main()
