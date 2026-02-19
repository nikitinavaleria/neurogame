import os
import sys
from pathlib import Path


APP_NAME = "NeuroGame"


def app_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.getenv("APPDATA")
        if base:
            root = Path(base)
        else:
            root = Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path.home() / ".local" / "share"
    primary = root / APP_NAME
    try:
        primary.mkdir(parents=True, exist_ok=True)
        return primary
    except OSError:
        fallback = Path.cwd() / "data" / "_appdata"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def app_data_path(*parts: str) -> Path:
    return app_data_dir().joinpath(*parts)


def bundled_data_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass) / "data"
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[1] / "data"


def bundled_data_path(*parts: str) -> Path:
    return bundled_data_dir().joinpath(*parts)


def bundled_resource_path(*parts: str) -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass).joinpath(*parts)
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parents[2].joinpath(*parts)
