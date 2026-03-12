import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class UserAgg:
    user_id: str
    sessions: int = 0
    total_tasks: int = 0
    accuracy_weighted_sum: float = 0.0
    rt_weighted_sum: float = 0.0
    rt_weight: int = 0
    best_level: int = 1
    partial_sessions: int = 0

    def add_session(self, payload: dict[str, Any]) -> None:
        tasks = int(payload.get("total_tasks", 0) or 0)
        accuracy = float(payload.get("accuracy_total", 0.0) or 0.0)
        mean_rt = float(payload.get("mean_rt", 0.0) or 0.0)
        last_level = int(payload.get("last_level", payload.get("max_level", 1)) or 1)
        is_partial = int(payload.get("is_partial", 0) or 0)

        self.sessions += 1
        self.total_tasks += max(0, tasks)
        self.accuracy_weighted_sum += max(0, tasks) * accuracy
        if mean_rt > 0 and tasks > 0:
            self.rt_weighted_sum += tasks * mean_rt
            self.rt_weight += tasks
        self.best_level = max(self.best_level, max(1, last_level))
        self.partial_sessions += 1 if is_partial else 0

    def to_row(self) -> dict[str, Any]:
        tasks = max(1, self.total_tasks)
        accuracy = self.accuracy_weighted_sum / tasks
        mean_rt = (self.rt_weighted_sum / self.rt_weight) if self.rt_weight > 0 else 0.0
        speed_score = max(0.0, 100.0 - (mean_rt / 30.0 if mean_rt > 0 else 0.0))
        score = (0.5 * (accuracy * 100.0)) + (0.3 * (self.best_level * 10.0)) + (0.2 * speed_score)
        return {
            "user_id": self.user_id,
            "score": round(score, 2),
            "best_level": int(self.best_level),
            "accuracy_pct": round(accuracy * 100.0, 2),
            "mean_rt_ms": round(mean_rt, 1),
            "sessions": int(self.sessions),
            "total_tasks": int(self.total_tasks),
            "partial_sessions": int(self.partial_sessions),
        }


def build_leaderboard(
    db_path: Path,
    limit: int = 100,
    min_tasks: int = 30,
) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []

    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        cur = conn.cursor()
        rows = cur.execute(
            """
            SELECT id, user_id, session_id, event_type, payload_json
            FROM events_raw
            WHERE event_type IN ('session_end', 'session_end_partial')
            ORDER BY id ASC
            """
        ).fetchall()

    # Дедупликация: по каждой сессии считаем только одну итоговую запись.
    # Приоритет у полного завершения (session_end) над частичным (session_end_partial).
    session_rows: dict[tuple[str, str], tuple[int, str, dict[str, Any]]] = {}
    fallback_rows: list[tuple[str, dict[str, Any]]] = []
    rank = {"session_end_partial": 1, "session_end": 2}

    for row_id, user_id, session_id, event_type, payload_json in rows:
        uid = str(user_id or "").strip() or "unknown"
        sid = str(session_id or "").strip()
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            continue
        payload_sid = str(payload.get("session_id", "")).strip()
        if payload_sid:
            sid = payload_sid
        if not sid:
            fallback_rows.append((uid, payload))
            continue

        key = (uid, sid)
        current_rank = rank.get(str(event_type), 0)
        prev = session_rows.get(key)
        if prev is None:
            session_rows[key] = (current_rank, str(event_type), payload)
            continue
        prev_rank = prev[0]
        # Если тип одинаковый, оставляем более позднюю запись (ORDER BY id ASC => последняя перезапишет).
        # Если тип разный, приоритет у session_end.
        if current_rank >= prev_rank:
            session_rows[key] = (current_rank, str(event_type), payload)

    users: dict[str, UserAgg] = {}
    effective_rows: list[tuple[str, dict[str, Any]]] = [
        (uid, payload) for (uid, _sid), (_r, _event_type, payload) in session_rows.items()
    ]
    effective_rows.extend(fallback_rows)

    for uid, payload in effective_rows:
        agg = users.setdefault(uid, UserAgg(user_id=uid))
        agg.add_session(payload)

    leaderboard = [agg.to_row() for agg in users.values() if agg.total_tasks >= max(0, int(min_tasks))]
    leaderboard.sort(
        key=lambda r: (-float(r["score"]), -int(r["best_level"]), -float(r["accuracy_pct"]), float(r["mean_rt_ms"]))
    )
    if limit > 0:
        leaderboard = leaderboard[:limit]

    for idx, row in enumerate(leaderboard, start=1):
        row["rank"] = idx
    return leaderboard
