from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request

from game.settings import SessionConfig
from training.bridge_transform import to_jsonl, transform_raw_events


@dataclass(frozen=True)
class PipelineConfig:
    server: str = "http://45.159.211.104:8000"
    api_key: str = os.getenv("NEUROGAME_API_KEY", "").strip()
    out_dir: str = "training/data"
    model_out_path: str = SessionConfig().rl_model_path
    page_size: int = 1000
    max_pages: int = 10000
    train_mode: str = "all"  # "all" | "baseline" | "ppo"
    epochs: int = 40
    batch_size: int = 64
    gamma: float = 0.97
    lr: float = 3e-4
    skip_train: bool = False


RUN_CONFIG = PipelineConfig()
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _join_base(base: str, path: str) -> str:
    base = base.rstrip("/")
    return f"{base}{path}"


def _http_get_json(url: str, timeout_sec: float = 10.0) -> dict[str, Any]:
    req = request.Request(url, method="GET")
    with request.urlopen(req, timeout=timeout_sec) as resp:
        if resp.status != 200:
            raise RuntimeError(f"http_status_{resp.status}")
        raw = resp.read().decode("utf-8") or "{}"
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise RuntimeError("invalid_json_payload")
        return data


def fetch_all_rows(server: str, api_key: str, page_size: int, max_pages: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    safe_page_size = max(1, min(5000, int(page_size)))
    safe_max_pages = max(1, int(max_pages))

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


def run_train(
    data_path: Path,
    out_model_path: Path,
    mode: str,
    epochs: int,
    batch_size: int,
    gamma: float,
    lr: float,
) -> None:
    cmd = [
        sys.executable,
        "-m",
        "training.train",
        "--data",
        str(data_path),
        "--out",
        str(out_model_path),
        "--mode",
        mode,
        "--epochs",
        str(epochs),
        "--batch-size",
        str(batch_size),
        "--gamma",
        str(gamma),
        "--lr",
        str(lr),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    cfg = RUN_CONFIG
    out_dir = Path(cfg.out_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

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
    events_path = out_dir / "events.jsonl"
    adaptations_path = out_dir / "adaptations.jsonl"
    sessions_path = out_dir / "sessions.jsonl"
    to_jsonl(events_path, events)
    to_jsonl(adaptations_path, adaptations)
    to_jsonl(sessions_path, sessions)

    print(
        "Prepared dataset: "
        f"raw={len(rows)}, events={len(events)}, adaptations={len(adaptations)}, sessions={len(sessions)}"
    )
    print(f"Saved: {events_path}")
    print(f"Saved: {adaptations_path}")
    print(f"Saved: {sessions_path}")

    if cfg.skip_train:
        return

    out_model_path = Path(cfg.model_out_path)
    if not out_model_path.is_absolute():
        out_model_path = PROJECT_ROOT / out_model_path
    run_train(
        data_path=adaptations_path,
        out_model_path=out_model_path,
        mode=cfg.train_mode,
        epochs=cfg.epochs,
        batch_size=cfg.batch_size,
        gamma=cfg.gamma,
        lr=cfg.lr,
    )


if __name__ == "__main__":
    main()
