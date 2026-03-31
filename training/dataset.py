import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class Transition:
    session_id: str
    state: List[float]
    action: int
    task_actions: List[int]
    reward: float
    next_state: List[float]
    done: bool


def load_adaptations(path: str) -> List[dict]:
    records = []
    p = Path(path)
    if not p.exists():
        return records
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    records.sort(key=lambda r: (str(r.get("session_id", "")), int(r.get("step", 0))))
    return records


def _same_episode(cur: dict, nxt: dict) -> bool:
    cur_sid = cur.get("session_id")
    nxt_sid = nxt.get("session_id")
    if cur_sid and nxt_sid:
        if cur_sid != nxt_sid:
            return False
        if cur.get("batch_index") is not None and nxt.get("batch_index") is not None:
            return cur.get("batch_index") == nxt.get("batch_index")
        return int(nxt.get("step", 0)) >= int(cur.get("step", 0))

    # Старые логи без session_id/batch_index: считаем эпизодом монотонную последовательность step.
    cur_step = int(cur.get("step", 0))
    nxt_step = int(nxt.get("step", 0))
    return nxt_step >= cur_step


def _normalize_action_id(rec: dict) -> int | None:
    action = rec.get("action_id")
    if action is None:
        return None
    try:
        action = int(action)
    except (TypeError, ValueError):
        return None

    # Новый формат: tempo-only (0,1,2)
    if rec.get("action_space") == "tempo3":
        return action if 0 <= action <= 2 else None

    # Старый формат: 3x3 (0..8) -> берем только компонент темпа.
    if 0 <= action <= 8:
        delta_tempo = (action % 3) - 1
        return delta_tempo + 1

    # Если уже нормализовано.
    if 0 <= action <= 2:
        return action
    return None


def _task_keys() -> List[str]:
    return ["compare_codes", "sequence_memory", "rule_switch", "parity_check", "radar_scan"]


def _extract_task_offsets(rec: dict) -> dict:
    payload = rec.get("task_offsets")
    if not isinstance(payload, dict):
        return {}
    out = {}
    for key in _task_keys():
        try:
            out[key] = int(payload.get(key, 0))
        except (TypeError, ValueError):
            out[key] = 0
    return out


def _task_actions_from_offsets(prev_offsets: dict, cur_offsets: dict) -> List[int]:
    actions: List[int] = []
    for key in _task_keys():
        prev_v = int(prev_offsets.get(key, 0))
        cur_v = int(cur_offsets.get(key, 0))
        delta = cur_v - prev_v
        if delta > 0:
            aid = 2
        elif delta < 0:
            aid = 0
        else:
            aid = 1
        actions.append(aid)
    return actions


def build_transitions(records: List[dict], modes: Optional[set] = None) -> List[Transition]:
    if modes is not None:
        records = [r for r in records if r.get("mode") in modes]
    transitions: List[Transition] = []
    last_offsets_by_session: dict[str, dict] = {}
    for i in range(len(records)):
        cur = records[i]
        state = cur.get("state")
        if not isinstance(state, list) or not state:
            continue
        action = _normalize_action_id(cur)
        reward = cur.get("reward")
        if action is None or reward is None:
            continue
        session_id = str(cur.get("session_id", "")).strip()
        prev_offsets = last_offsets_by_session.get(session_id, {})
        cur_offsets = _extract_task_offsets(cur)
        task_actions = _task_actions_from_offsets(prev_offsets, cur_offsets)
        if session_id:
            last_offsets_by_session[session_id] = cur_offsets

        if i + 1 < len(records) and _same_episode(cur, records[i + 1]):
            nxt = records[i + 1]
            next_state = nxt.get("state", state)
            done = False
        else:
            next_state = state
            done = True

        if not isinstance(next_state, list) or len(next_state) != len(state):
            next_state = state

        transitions.append(
            Transition(
                session_id=session_id,
                state=state,
                action=int(action),
                task_actions=task_actions,
                reward=float(reward),
                next_state=next_state,
                done=done,
            )
        )
    return transitions
