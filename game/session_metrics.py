from __future__ import annotations

from game.runtime.models import TaskResult


def task_title(task_id: str) -> str:
    return {
        "compare_codes": "Сравнение кодов",
        "sequence_memory": "Память",
        "rule_switch": "Смена правила",
        "parity_check": "Четность числа",
        "radar_scan": "Радарный сигнал",
    }.get(task_id, task_id)


def compute_reward(acc: float, mean_rt: float) -> float:
    reward = acc - 0.7
    if mean_rt > 1000:
        reward -= 0.0004 * (mean_rt - 1000)
    return reward


def compute_fatigue_trend(window: list[TaskResult]) -> float:
    rts = [r.rt_ms for r in window if r.rt_ms is not None]
    if len(rts) < 2:
        return 0.0
    n = len(rts)
    xs = list(range(n))
    mean_x = (n - 1) / 2
    mean_y = sum(rts) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, rts))
    den = sum((x - mean_x) ** 2 for x in xs) or 1.0
    return num / den


def compute_switch_cost(window: list[TaskResult]) -> float:
    switch_rts = []
    nonswitch_rts = []
    prev_rule = None
    for result in window:
        if result.task_id != "rule_switch":
            continue
        rule = result.payload.get("rule")
        if rule is None or result.rt_ms is None:
            continue
        if prev_rule is not None and rule != prev_rule:
            switch_rts.append(result.rt_ms)
        else:
            nonswitch_rts.append(result.rt_ms)
        prev_rule = rule
    if not switch_rts or not nonswitch_rts:
        return 0.0
    return (sum(switch_rts) / len(switch_rts)) - (sum(nonswitch_rts) / len(nonswitch_rts))


def build_state_vector(
    window: list[TaskResult],
    current_level: int,
    event_rate_sec: float,
    time_pressure: float,
    parallel_streams: int,
    task_mix: tuple,
) -> list[float]:
    acc = sum(1 for r in window if r.correct) / len(window)
    rts = [r.rt_ms for r in window if r.rt_ms is not None]
    mean_rt = sum(rts) / len(rts) if rts else 0.0
    std_rt = 0.0
    if len(rts) > 1:
        mean = mean_rt
        std_rt = (sum((x - mean) ** 2 for x in rts) / len(rts)) ** 0.5

    error_streak = 0
    for r in reversed(window):
        if r.correct:
            break
        error_streak += 1

    switch_cost = compute_switch_cost(window)
    fatigue_trend = compute_fatigue_trend(window)
    return [
        acc,
        mean_rt,
        std_rt,
        float(error_streak),
        switch_cost,
        fatigue_trend,
        float(current_level),
        event_rate_sec,
        time_pressure,
        float(parallel_streams),
        float(task_mix[0]),
        float(task_mix[1]),
    ]


def compute_zone_quality(window: list[TaskResult]) -> float:
    if not window:
        return 0.0
    accuracy = sum(1 for r in window if r.correct) / len(window)
    rts = [r.rt_ms for r in window if r.rt_ms is not None]
    if not rts:
        return max(0.0, min(1.0, accuracy))
    mean_rt = sum(rts) / len(rts)
    rt_penalty = max(0.0, min(0.5, (mean_rt - 1400.0) / 2200.0))
    return max(0.0, min(1.0, accuracy - rt_penalty))


def count_successes(window: list[TaskResult]) -> int:
    if not window:
        return 0
    return sum(1 for r in window if r.correct and not r.is_timeout)


def compute_flight_progress(successes: int, total_tasks: int) -> float:
    return max(0.0, min(1.0, successes / max(1, total_tasks)))
