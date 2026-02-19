from __future__ import annotations

import json
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
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _infer_mode(model_version: Any, payload: dict[str, Any]) -> str:
    if isinstance(payload.get("mode"), str):
        return payload["mode"]
    if isinstance(model_version, str) and "ppo" in model_version.lower():
        return "ppo"
    return "baseline"


def transform_raw_events(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    event_records: list[dict[str, Any]] = []
    adaptation_records: list[dict[str, Any]] = []
    session_records: list[dict[str, Any]] = []

    for row in rows:
        event_id = row.get("event_id")
        event_type = row.get("event_type")
        event_ts = row.get("event_ts")
        user_id = row.get("user_id")
        session_id = row.get("session_id")
        model_version = row.get("model_version")
        payload = _as_dict(row.get("payload"))
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

        if event_type in ("session_end", "session_end_partial"):
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

    return event_records, adaptation_records, session_records
