import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class Transition:
    state: List[float]
    action: int
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


def build_transitions(records: List[dict], modes: Optional[set] = None) -> List[Transition]:
    if modes is not None:
        records = [r for r in records if r.get("mode") in modes]
    transitions: List[Transition] = []
    for i in range(len(records)):
        cur = records[i]
        state = cur.get("state")
        if not isinstance(state, list) or not state:
            continue
        action = _normalize_action_id(cur)
        reward = cur.get("reward")
        if action is None or reward is None:
            continue

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
                state=state,
                action=int(action),
                reward=float(reward),
                next_state=next_state,
                done=done,
            )
        )
    return transitions
