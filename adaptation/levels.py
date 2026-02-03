from dataclasses import replace

from config.settings import DifficultyConfig


def apply_level(base: DifficultyConfig, level: int) -> DifficultyConfig:
    # Скорость: чем выше уровень, тем быстрее.
    speed_factor = max(0.6, 1.0 - 0.05 * (level - 1))
    time_pressure = max(0.8, base.global_params.time_pressure * speed_factor)
    event_rate = max(1.2, base.global_params.event_rate_sec * speed_factor)

    # Сложность задач: чем выше уровень, тем длиннее/сложнее.
    code_len = min(7, base.compare.code_len + (level // 2))
    similarity = min(0.7, base.compare.similarity_rate + 0.02 * (level - 1))
    compare_time = max(900, int(base.compare.time_limit_ms * speed_factor))

    seq_len = min(8, base.memory.seq_len + (level // 2))
    memory_time = max(1200, int(base.memory.time_limit_ms * speed_factor))

    switch_rate = min(0.6, base.switch.rule_switch_rate + 0.03 * (level - 1))
    switch_time = max(900, int(base.switch.time_limit_ms * speed_factor))

    return DifficultyConfig(
        global_params=replace(
            base.global_params,
            event_rate_sec=event_rate,
            time_pressure=time_pressure,
        ),
        compare=replace(
            base.compare,
            code_len=code_len,
            similarity_rate=similarity,
            time_limit_ms=compare_time,
        ),
        memory=replace(
            base.memory,
            seq_len=seq_len,
            time_limit_ms=memory_time,
        ),
        switch=replace(
            base.switch,
            rule_switch_rate=switch_rate,
            time_limit_ms=switch_time,
        ),
    )


def apply_tempo(diff: DifficultyConfig, tempo_offset: int) -> DifficultyConfig:
    # tempo_offset: -2 (slower) .. +2 (faster)
    factor = max(0.6, 1.0 - 0.08 * tempo_offset)
    return DifficultyConfig(
        global_params=replace(
            diff.global_params,
            event_rate_sec=max(1.0, diff.global_params.event_rate_sec * factor),
            time_pressure=max(0.8, diff.global_params.time_pressure * factor),
        ),
        compare=replace(diff.compare, time_limit_ms=max(900, int(diff.compare.time_limit_ms * factor))),
        memory=replace(diff.memory, time_limit_ms=max(1200, int(diff.memory.time_limit_ms * factor))),
        switch=replace(diff.switch, time_limit_ms=max(900, int(diff.switch.time_limit_ms * factor))),
    )
