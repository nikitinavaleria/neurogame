from __future__ import annotations

import os
import sys
from pathlib import Path


def load_env_defaults() -> None:
    """Load NEUROGAME_* defaults from .env files without overriding existing env."""
    for env_path in _candidate_env_paths():
        _load_env_file(env_path)


def _candidate_env_paths() -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    candidates = [
        Path.cwd() / ".env",
        Path(sys.executable).resolve().parent / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / ".env")
    for item in candidates:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        paths.append(item)
    return paths


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.startswith("NEUROGAME_"):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ.setdefault(key, value)
