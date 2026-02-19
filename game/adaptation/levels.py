from dataclasses import replace

from game.settings import DifficultyConfig


def apply_level(base: DifficultyConfig, level: int) -> DifficultyConfig:
    # Скорость: на высоких уровнях рост темпа замедляется, чтобы не было резкого "обрыва" по времени.
    if level <= 5:
        speed_factor = 1.0 - 0.035 * (level - 1)
    else:
        speed_factor = 1.0 - 0.035 * 4 - 0.015 * (level - 5)
    speed_factor = max(0.82, speed_factor)
    # time_pressure оставляем стабильным, иначе дедлайны сжимаются слишком агрессивно.
    time_pressure = base.global_params.time_pressure
    event_rate = max(1.4, base.global_params.event_rate_sec * speed_factor)

    # Сложность задач: чем выше уровень, тем длиннее/сложнее.
    code_len = min(7, base.compare.code_len + (level // 2))
    similarity = min(0.7, base.compare.similarity_rate + 0.02 * (level - 1))
    first_level_bonus = 1.25 if level == 1 else 1.0
    compare_time = max(900, int(base.compare.time_limit_ms * speed_factor * first_level_bonus))

    seq_len = min(8, base.memory.seq_len + (level // 2))
    memory_time = max(1200, int(base.memory.time_limit_ms * speed_factor * first_level_bonus))

    switch_rate = min(0.6, base.switch.rule_switch_rate + 0.03 * (level - 1))
    rule_complexity = min(7, base.switch.rule_complexity + (level // 2))
    switch_time = max(900, int(base.switch.time_limit_ms * speed_factor * first_level_bonus))

    parity_min = max(-999, base.parity.min_value - max(0, level - 5) * 10)
    parity_max = min(999, base.parity.max_value + (level - 1) * 40)
    parity_question_complexity = min(7, base.parity.question_complexity + (level // 2))
    parity_time = max(900, int(base.parity.time_limit_ms * speed_factor * first_level_bonus))

    radar_len = min(9, base.radar.signal_len + (level // 2))
    radar_target_pool_size = min(7, base.radar.target_pool_size + (level // 2))
    radar_time = max(900, int(base.radar.time_limit_ms * speed_factor * first_level_bonus))

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
            rule_complexity=rule_complexity,
            time_limit_ms=switch_time,
        ),
        parity=replace(
            base.parity,
            min_value=parity_min,
            max_value=parity_max,
            question_complexity=parity_question_complexity,
            time_limit_ms=parity_time,
        ),
        radar=replace(
            base.radar,
            signal_len=radar_len,
            target_pool_size=radar_target_pool_size,
            time_limit_ms=radar_time,
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
        parity=replace(diff.parity, time_limit_ms=max(900, int(diff.parity.time_limit_ms * factor))),
        radar=replace(diff.radar, time_limit_ms=max(900, int(diff.radar.time_limit_ms * factor))),
    )
