import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class SessionStats:
    mode: str
    accuracy_total: float
    mean_rt: float
    rt_variance: float
    answered_rate: float
    level_gain: float


def load_events(path: str) -> List[dict]:
    p = Path(path)
    if not p.exists():
        return []
    records: List[dict] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def split_by_session(events: List[dict]) -> Dict[str, List[dict]]:
    sessions: Dict[str, List[dict]] = {}
    for e in events:
        sid = str(e.get("session_id", "unknown"))
        sessions.setdefault(sid, []).append(e)
    return sessions


def summarize_session(events: List[dict]) -> SessionStats:
    mode = str(events[0].get("mode", "unknown")) if events else "unknown"
    total = len(events) if events else 1
    correct = sum(1 for e in events if int(e.get("correct", 0)) == 1)
    accuracy = correct / total
    answered_rate = sum(1 for e in events if int(e.get("deadline_met", 0)) == 1) / total
    rts = [e.get("reaction_time") for e in events if e.get("reaction_time") is not None]
    mean_rt = (sum(rts) / len(rts)) if rts else 0.0
    if len(rts) > 1:
        rt_var = sum((x - mean_rt) ** 2 for x in rts) / len(rts)
    else:
        rt_var = 0.0
    levels = [int(e.get("level", 1)) for e in events if e.get("level") is not None]
    level_gain = float(levels[-1] - levels[0]) if levels else 0.0
    return SessionStats(
        mode=mode,
        accuracy_total=accuracy,
        mean_rt=mean_rt,
        rt_variance=rt_var,
        answered_rate=answered_rate,
        level_gain=level_gain,
    )


def metric_values(stats: List[SessionStats], metric: str) -> List[float]:
    return [float(getattr(s, metric)) for s in stats]


def permutation_pvalue(
    baseline: List[float],
    adaptive: List[float],
    higher_is_better: bool,
    n_perm: int = 5000,
    seed: int = 42,
) -> Tuple[float, float]:
    if not baseline or not adaptive:
        return 0.0, 1.0
    obs = (sum(adaptive) / len(adaptive)) - (sum(baseline) / len(baseline))
    pooled = baseline + adaptive
    n_b = len(baseline)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        b = pooled[:n_b]
        a = pooled[n_b:]
        diff = (sum(a) / len(a)) - (sum(b) / len(b))
        if higher_is_better:
            if diff >= obs:
                extreme += 1
        else:
            if diff <= obs:
                extreme += 1
    p = (extreme + 1) / (n_perm + 1)
    return obs, p


def print_metric_report(name: str, baseline: List[float], adaptive: List[float], higher_is_better: bool) -> None:
    if not baseline or not adaptive:
        print(f"- {name}: недостаточно данных для сравнения")
        return
    b_mean = sum(baseline) / len(baseline)
    a_mean = sum(adaptive) / len(adaptive)
    delta, p_value = permutation_pvalue(baseline, adaptive, higher_is_better=higher_is_better)
    if higher_is_better:
        better = a_mean > b_mean
    else:
        better = a_mean < b_mean
    verdict = "лучше" if better else "не лучше"
    print(
        f"- {name}: baseline={b_mean:.4f}, adaptive={a_mean:.4f}, "
        f"delta={delta:.4f}, p={p_value:.4f} -> adaptive {verdict}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate baseline vs adaptive sessions")
    parser.add_argument("--events", default="data/events.jsonl")
    args = parser.parse_args()

    events = load_events(args.events)
    if not events:
        print(f"Нет данных: {args.events}")
        return

    sessions = split_by_session(events)
    summaries = [summarize_session(evts) for evts in sessions.values() if evts]
    baseline_stats = [s for s in summaries if s.mode == "baseline"]
    adaptive_stats = [s for s in summaries if s.mode == "ppo"]

    print(f"Сессий baseline: {len(baseline_stats)}")
    print(f"Сессий adaptive(ppo): {len(adaptive_stats)}")

    print_metric_report(
        "accuracy_total",
        metric_values(baseline_stats, "accuracy_total"),
        metric_values(adaptive_stats, "accuracy_total"),
        higher_is_better=True,
    )
    print_metric_report(
        "mean_rt",
        metric_values(baseline_stats, "mean_rt"),
        metric_values(adaptive_stats, "mean_rt"),
        higher_is_better=False,
    )
    print_metric_report(
        "rt_variance",
        metric_values(baseline_stats, "rt_variance"),
        metric_values(adaptive_stats, "rt_variance"),
        higher_is_better=False,
    )
    print_metric_report(
        "answered_rate",
        metric_values(baseline_stats, "answered_rate"),
        metric_values(adaptive_stats, "answered_rate"),
        higher_is_better=True,
    )
    print_metric_report(
        "level_gain",
        metric_values(baseline_stats, "level_gain"),
        metric_values(adaptive_stats, "level_gain"),
        higher_is_better=True,
    )


if __name__ == "__main__":
    main()
