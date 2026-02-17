import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


def load_events(path: str) -> List[dict]:
    p = Path(path)
    if not p.exists():
        print(f"No events file found at {path}")
        return []
    records = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def split_by_session(events: List[dict]) -> Dict[str, List[dict]]:
    sessions = defaultdict(list)
    for e in events:
        sessions[e.get("session_id", "unknown")].append(e)
    return sessions


def compute_accuracy(events: List[dict]) -> float:
    if not events:
        return 0.0
    correct = sum(1 for e in events if e.get("correct") == 1)
    return correct / len(events)


def compute_rt_stats(events: List[dict]) -> Tuple[float, float]:
    rts = [e.get("reaction_time") for e in events if e.get("reaction_time") is not None]
    if not rts:
        return 0.0, 0.0
    mean_rt = sum(rts) / len(rts)
    var_rt = 0.0
    if len(rts) > 1:
        var_rt = sum((x - mean_rt) ** 2 for x in rts) / len(rts)
    return mean_rt, var_rt


def compute_fatigue_trend(events: List[dict]) -> float:
    rts = [e.get("reaction_time") for e in events if e.get("reaction_time") is not None]
    if len(rts) < 2:
        return 0.0
    n = len(rts)
    xs = list(range(n))
    mean_x = (n - 1) / 2
    mean_y = sum(rts) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, rts))
    den = sum((x - mean_x) ** 2 for x in xs) or 1.0
    return num / den


def compute_switch_cost(events: List[dict]) -> float:
    switch_rts = []
    nonswitch_rts = []
    prev_rule = None
    for e in events:
        if e.get("task_id") != "rule_switch":
            continue
        payload = e.get("payload") or {}
        rule = payload.get("rule")
        rt = e.get("reaction_time")
        if rule is None or rt is None:
            continue
        if prev_rule is not None and rule != prev_rule:
            switch_rts.append(rt)
        else:
            nonswitch_rts.append(rt)
        prev_rule = rule
    if not switch_rts or not nonswitch_rts:
        return 0.0
    return (sum(switch_rts) / len(switch_rts)) - (sum(nonswitch_rts) / len(nonswitch_rts))


def summarize_session(events: List[dict]) -> dict:
    accuracy = compute_accuracy(events)
    mean_rt, var_rt = compute_rt_stats(events)
    batches: Dict[int, List[dict]] = defaultdict(list)
    for e in events:
        b = e.get("batch_index")
        if b is None:
            continue
        try:
            b = int(b)
        except (TypeError, ValueError):
            continue
        batches[b].append(e)

    if not batches and events:
        # Совместимость со старыми логами: если batch_index отсутствует,
        # разбиваем на псевдо-батчи по 10 задач.
        for i, e in enumerate(events):
            batches[(i // 10) + 1].append(e)

    active_batches = 0
    idle_batches = 0
    levels = [int(e.get("level", 1)) for e in events if e.get("level") is not None]
    answered_rate = 0.0
    if events:
        answered_rate = sum(1 for e in events if int(e.get("deadline_met", 0)) == 1) / len(events)
    for _, batch_events in batches.items():
        answered = sum(1 for e in batch_events if int(e.get("deadline_met", 0)) == 1)
        if answered > 0:
            active_batches += 1
        else:
            idle_batches += 1

    level_gain = 0
    if levels:
        level_gain = levels[-1] - levels[0]

    return {
        "accuracy_total": accuracy,
        "mean_rt": mean_rt,
        "rt_variance": var_rt,
        "switch_cost": compute_switch_cost(events),
        "fatigue_trend": compute_fatigue_trend(events),
        "answered_rate": answered_rate,
        "active_batches": active_batches,
        "idle_batches": idle_batches,
        "level_gain": level_gain,
        "mode": events[0].get("mode", "unknown") if events else "unknown",
    }


def aggregate_by_mode(summaries: Dict[str, dict]) -> Dict[str, dict]:
    grouped = defaultdict(list)
    for s in summaries.values():
        grouped[s["mode"]].append(s)

    results = {}
    for mode, items in grouped.items():
        if not items:
            continue
        results[mode] = {
            "sessions": len(items),
            "accuracy_total": sum(i["accuracy_total"] for i in items) / len(items),
            "mean_rt": sum(i["mean_rt"] for i in items) / len(items),
            "rt_variance": sum(i["rt_variance"] for i in items) / len(items),
            "switch_cost": sum(i["switch_cost"] for i in items) / len(items),
            "fatigue_trend": sum(i["fatigue_trend"] for i in items) / len(items),
            "answered_rate": sum(i["answered_rate"] for i in items) / len(items),
            "active_batches": sum(i["active_batches"] for i in items) / len(items),
            "idle_batches": sum(i["idle_batches"] for i in items) / len(items),
            "level_gain": sum(i["level_gain"] for i in items) / len(items),
        }
    return results


def print_report(summaries: Dict[str, dict]) -> None:
    if not summaries:
        print("No sessions found.")
        return

    print("Session metrics:")
    for session_id, s in summaries.items():
        print(
            f"- {session_id} [{s['mode']}] "
            f"acc={s['accuracy_total']:.3f} "
            f"rt={s['mean_rt']:.1f} "
            f"var={s['rt_variance']:.1f} "
            f"switch={s['switch_cost']:.1f} "
            f"fatigue={s['fatigue_trend']:.3f} "
            f"answered={s['answered_rate']:.3f} "
            f"active_batches={s['active_batches']} "
            f"idle_batches={s['idle_batches']} "
            f"level_gain={s['level_gain']}"
        )

    print("\nAggregate by mode:")
    agg = aggregate_by_mode(summaries)
    for mode, s in agg.items():
        print(
            f"- {mode} (n={s['sessions']}): "
            f"acc={s['accuracy_total']:.3f} "
            f"rt={s['mean_rt']:.1f} "
            f"var={s['rt_variance']:.1f} "
            f"switch={s['switch_cost']:.1f} "
            f"fatigue={s['fatigue_trend']:.3f} "
            f"answered={s['answered_rate']:.3f} "
            f"active_batches={s['active_batches']:.2f} "
            f"idle_batches={s['idle_batches']:.2f} "
            f"level_gain={s['level_gain']:.2f}"
        )


def main() -> None:
    events = load_events("data/events.jsonl")
    sessions = split_by_session(events)
    summaries = {sid: summarize_session(evts) for sid, evts in sessions.items()}
    print_report(summaries)


if __name__ == "__main__":
    main()
