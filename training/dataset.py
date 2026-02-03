import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


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
    return records


def build_transitions(records: List[dict]) -> List[Transition]:
    transitions: List[Transition] = []
    for i in range(len(records) - 1):
        cur = records[i]
        nxt = records[i + 1]
        transitions.append(
            Transition(
                state=cur["state"],
                action=cur["action_id"],
                reward=cur["reward"],
                next_state=nxt["state"],
                done=False,
            )
        )
    return transitions
