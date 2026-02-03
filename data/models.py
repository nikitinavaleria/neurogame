from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    created_ms: int
    deadline_ms: int
    difficulty: Dict[str, Any]
    payload: Dict[str, Any]


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    created_ms: int
    finished_ms: int
    response: Optional[str]
    correct: bool
    rt_ms: Optional[int]
    is_timeout: bool
    difficulty: Dict[str, Any]
    payload: Dict[str, Any]


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    total_tasks: int
    accuracy_total: float
    mean_rt: float
    rt_variance: float
    switch_cost: float
    fatigue_trend: float
    overload_events: int
