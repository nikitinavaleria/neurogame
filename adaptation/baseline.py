from dataclasses import dataclass

from config.settings import DifficultyConfig, LevelConfig


@dataclass
class BaselineState:
    level: int
    tempo_offset: int


@dataclass
class BaselineAdapter:
    """
    Эвристический baseline.
    На старте возвращает неизмененную сложность.
    Позже можно добавить правила повышения/понижения.
    """

    difficulty: DifficultyConfig
    level_cfg: LevelConfig
    state: BaselineState

    def update(self, accuracy: float, mean_rt: float) -> tuple:
        level = self.state.level
        tempo = self.state.tempo_offset
        if accuracy >= self.level_cfg.up_accuracy and mean_rt <= self.level_cfg.up_rt_ms:
            level = min(self.level_cfg.max_level, level + 1)
            tempo = min(2, tempo + 1)
        elif accuracy <= self.level_cfg.down_accuracy or mean_rt >= self.level_cfg.down_rt_ms:
            level = max(self.level_cfg.min_level, level - 1)
            tempo = max(-2, tempo - 1)
        self.state.level = level
        self.state.tempo_offset = tempo
        return level, tempo
