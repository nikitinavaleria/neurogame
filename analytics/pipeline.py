from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from analytics.eval_adaptation import compare_modes, permutation_pvalue
from analytics.metrics import aggregate_by_mode, build_session_summaries, load_events, print_report
from analytics.raw_transform import to_jsonl, transform_raw_events


@dataclass(frozen=True)
class AnalyticsConfig:
    fetch_from_backend: bool = True
    server: str = "http://127.0.0.1:8000"
    api_key: str = "dev-key-change-me"
    page_size: int = 1000
    max_pages: int = 10000
    dataset_dir: str = "analytics/data"
    reports_dir: str = "analytics/reports"


RUN_CONFIG = AnalyticsConfig()


def _join_base(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"


def _http_get_json(url: str, timeout_sec: float = 10.0) -> dict[str, Any]:
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=timeout_sec) as resp:
        if resp.status != 200:
            raise RuntimeError(f"http_status_{resp.status}")
        raw = resp.read().decode("utf-8") or "{}"
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("invalid_json_payload")
        return payload


def fetch_all_rows(server: str, api_key: str, page_size: int, max_pages: int) -> list[dict[str, Any]]:
    safe_page_size = max(1, min(5000, int(page_size)))
    safe_max_pages = max(1, int(max_pages))
    offset = 0
    rows: list[dict[str, Any]] = []

    for _ in range(safe_max_pages):
        query = parse.urlencode({"api_key": api_key, "limit": safe_page_size, "offset": offset})
        url = _join_base(server, f"/v1/export/raw?{query}")
        payload = _http_get_json(url)
        if payload.get("ok") is not True:
            raise RuntimeError("server_export_failed")
        page_rows = payload.get("rows", [])
        if not isinstance(page_rows, list):
            raise RuntimeError("server_rows_not_list")
        page_rows = [r for r in page_rows if isinstance(r, dict)]
        if not page_rows:
            break
        rows.extend(page_rows)
        offset += len(page_rows)
        if len(page_rows) < safe_page_size:
            break
    return rows


def _metric_result(baseline: list[float], adaptive: list[float], higher_is_better: bool) -> dict[str, float]:
    if not baseline or not adaptive:
        return {"baseline_mean": 0.0, "adaptive_mean": 0.0, "delta": 0.0, "p_value": 1.0}
    b_mean = sum(baseline) / len(baseline)
    a_mean = sum(adaptive) / len(adaptive)
    delta, p_value = permutation_pvalue(baseline, adaptive, higher_is_better=higher_is_better)
    return {
        "baseline_mean": b_mean,
        "adaptive_mean": a_mean,
        "delta": delta,
        "p_value": p_value,
    }


def build_comparison_report(events: list[dict[str, Any]]) -> dict[str, Any]:
    raw = compare_modes(events)
    return {
        "baseline_sessions": raw["baseline_sessions"],
        "adaptive_sessions": raw["adaptive_sessions"],
        "accuracy_total": _metric_result(
            raw["accuracy_total"]["baseline"],
            raw["accuracy_total"]["adaptive"],
            higher_is_better=True,
        ),
        "mean_rt": _metric_result(
            raw["mean_rt"]["baseline"],
            raw["mean_rt"]["adaptive"],
            higher_is_better=False,
        ),
        "rt_variance": _metric_result(
            raw["rt_variance"]["baseline"],
            raw["rt_variance"]["adaptive"],
            higher_is_better=False,
        ),
        "answered_rate": _metric_result(
            raw["answered_rate"]["baseline"],
            raw["answered_rate"]["adaptive"],
            higher_is_better=True,
        ),
        "level_gain": _metric_result(
            raw["level_gain"]["baseline"],
            raw["level_gain"]["adaptive"],
            higher_is_better=True,
        ),
    }


def main() -> None:
    cfg = RUN_CONFIG
    dataset_dir = Path(cfg.dataset_dir)
    dataset_dir.mkdir(parents=True, exist_ok=True)
    events_path = dataset_dir / "events.jsonl"
    adaptations_path = dataset_dir / "adaptations.jsonl"
    sessions_path = dataset_dir / "sessions.jsonl"

    if cfg.fetch_from_backend:
        try:
            rows = fetch_all_rows(
                server=cfg.server,
                api_key=cfg.api_key,
                page_size=cfg.page_size,
                max_pages=cfg.max_pages,
            )
        except (error.URLError, error.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Fetch failed: {exc}")

        events, adaptations, sessions = transform_raw_events(rows)
        to_jsonl(events_path, events)
        to_jsonl(adaptations_path, adaptations)
        to_jsonl(sessions_path, sessions)
        print(
            "Dataset refreshed from backend: "
            f"raw={len(rows)}, events={len(events)}, adaptations={len(adaptations)}, sessions={len(sessions)}"
        )

    events = load_events(str(events_path))
    if not events:
        raise SystemExit(f"No events found at {events_path}")

    summaries = build_session_summaries(events)
    agg = aggregate_by_mode(summaries)
    comparison = build_comparison_report(events)

    reports_dir = Path(cfg.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    per_session_path = reports_dir / "session_metrics.json"
    by_mode_path = reports_dir / "mode_aggregate.json"
    compare_path = reports_dir / "mode_comparison.json"

    per_session_path.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    by_mode_path.write_text(json.dumps(agg, ensure_ascii=False, indent=2), encoding="utf-8")
    compare_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")

    print_report(summaries)
    print(f"\nSaved: {per_session_path}")
    print(f"Saved: {by_mode_path}")
    print(f"Saved: {compare_path}")


if __name__ == "__main__":
    main()
