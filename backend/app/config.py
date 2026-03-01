import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    api_key: str
    db_path: Path


def load_settings() -> Settings:
    root_dir = Path(__file__).resolve().parents[2]
    db_default = root_dir / "backend" / "data" / "events.db"
    db_path = Path(os.getenv("NEUROGAME_DB_PATH", str(db_default))).expanduser()
    api_key = os.getenv("NEUROGAME_API_KEY", "").strip()
    return Settings(api_key=api_key, db_path=db_path)
