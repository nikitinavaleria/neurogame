from dataclasses import dataclass
from typing import Optional, List


@dataclass
class BlockParams:
    """
    Настройки одного блока игры
    """
    n_trials: int = 40
    tasks_enabled: List[str] = None   # ["COLOR", "SHAPE"]
    switch_rate: float = 0.3          # от 0 до 1

    # тайминги (мс)
    cue_ms: int = 400
    time_limit_ms: int = 1500
    feedback_ms: int = 300
    iti_ms: int = 300


@dataclass
class TrialSpec:
    """
    Что нужно показать в конкретном trial-е
    """
    trial_index: int
    task_id: str               # "COLOR" или "SHAPE"
    stimulus: object           # объект Stimulus
    correct_action: str        # "F", "J", "K", "L"
    is_switch: bool


@dataclass
class TrialEvent:
    """
    Результат попытки - Что сделал игрок в trial-е
    """
    trial_index: int
    task_id: str
    is_switch: bool

    correct_action: str
    response_action: Optional[str]  # None если не нажал
    is_correct: bool

    rt_ms: Optional[int]             # None если не было ответа
    is_timeout: bool
