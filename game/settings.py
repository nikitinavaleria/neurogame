from dataclasses import dataclass


@dataclass(frozen=True)
class WindowConfig:
    width: int = 1600
    height: int = 900
    fps: int = 60
    title: str = "Deep Space Ops"


@dataclass(frozen=True)
class SessionConfig:
    total_tasks: int = 10
    overload_window: int = 10
    overload_accuracy_threshold: float = 0.5
    inter_task_pause_ms: int = 0
    adaptation_mode: str = "baseline"  # "baseline" or "ppo"
    rl_model_path: str = "game/assets/models/ppo_agent.pt"


@dataclass(frozen=True)
class GlobalDifficulty:
    event_rate_sec: float = 4.0
    parallel_streams: int = 1
    time_pressure: float = 1.4
    task_mix: tuple = (0.24, 0.2, 0.2, 0.18, 0.18)  # compare / memory / switch / parity / radar


@dataclass(frozen=True)
class CompareCodesDifficulty:
    code_len: int = 4
    similarity_rate: float = 0.35
    time_limit_ms: int = 3200


@dataclass(frozen=True)
class SequenceMemoryDifficulty:
    seq_len: int = 4
    retention_delay_ms: int = 0
    time_limit_ms: int = 4200


@dataclass(frozen=True)
class RuleSwitchDifficulty:
    rule_switch_rate: float = 0.25
    stimulus_rate_sec: float = 2.0
    rule_complexity: int = 2
    time_limit_ms: int = 3200


@dataclass(frozen=True)
class ParityDifficulty:
    min_value: int = 10
    max_value: int = 99
    question_complexity: int = 1
    time_limit_ms: int = 3000


@dataclass(frozen=True)
class RadarDifficulty:
    signal_len: int = 5
    threat_rate: float = 0.35
    target_pool_size: int = 1
    time_limit_ms: int = 3200


@dataclass(frozen=True)
class DifficultyConfig:
    global_params: GlobalDifficulty = GlobalDifficulty()
    compare: CompareCodesDifficulty = CompareCodesDifficulty()
    memory: SequenceMemoryDifficulty = SequenceMemoryDifficulty()
    switch: RuleSwitchDifficulty = RuleSwitchDifficulty()
    parity: ParityDifficulty = ParityDifficulty()
    radar: RadarDifficulty = RadarDifficulty()


@dataclass(frozen=True)
class LevelConfig:
    min_level: int = 1
    max_level: int = 10
    start_level: int = 1
    check_every: int = 3
    window_size: int = 8
    up_accuracy: float = 0.8
    down_accuracy: float = 0.65
    up_rt_ms: int = 1700
    down_rt_ms: int = 1900
    phase_up_accuracy: float = 0.75
    baseline_required_correct: int = 9
