from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_pending_runs(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    runs = payload.get("runs")
    if isinstance(runs, dict):
        return runs
    return {}


def save_pending_runs(path: Path, runs: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"runs": runs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
