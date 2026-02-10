from dataclasses import dataclass


@dataclass(frozen=True)
class WindowConfig:
    width: int = 1280
    height: int = 720
    fps: int = 60
    title: str = "Deep Space Ops"


@dataclass(frozen=True)
class SessionConfig:
    total_tasks: int = 120
    overload_window: int = 10
    overload_accuracy_threshold: float = 0.5
    inter_task_pause_ms: int = 600
    adaptation_mode: str = "baseline"  # "baseline" or "ppo"
    rl_model_path: str = "data/ppo_agent.pt"


@dataclass(frozen=True)
class GlobalDifficulty:
    event_rate_sec: float = 4.0
    parallel_streams: int = 1
    time_pressure: float = 1.4
    task_mix: tuple = (0.4, 0.3, 0.3)  # compare / memory / switch


@dataclass(frozen=True)
class CompareCodesDifficulty:
    code_len: int = 4
    similarity_rate: float = 0.35
    time_limit_ms: int = 3200


@dataclass(frozen=True)
class SequenceMemoryDifficulty:
    seq_len: int = 4
    retention_delay_ms: int = 1200
    time_limit_ms: int = 4200


@dataclass(frozen=True)
class RuleSwitchDifficulty:
    rule_switch_rate: float = 0.25
    stimulus_rate_sec: float = 2.0
    rule_complexity: int = 2
    time_limit_ms: int = 3200


@dataclass(frozen=True)
class DifficultyConfig:
    global_params: GlobalDifficulty = GlobalDifficulty()
    compare: CompareCodesDifficulty = CompareCodesDifficulty()
    memory: SequenceMemoryDifficulty = SequenceMemoryDifficulty()
    switch: RuleSwitchDifficulty = RuleSwitchDifficulty()


@dataclass(frozen=True)
class LevelConfig:
    min_level: int = 1
    max_level: int = 10
    start_level: int = 1
    check_every: int = 10
    window_size: int = 20
    up_accuracy: float = 0.85
    down_accuracy: float = 0.65
    up_rt_ms: int = 1000
    down_rt_ms: int = 1500
