from __future__ import annotations

import json
from pathlib import Path


def load_telemetry_settings(
    settings_path: Path,
    default_url: str,
    default_key: str,
    env_url: str = "",
    env_key: str = "",
) -> tuple[str, str]:
    env_url = (env_url or "").strip()
    env_key = (env_key or "").strip()

    resolved_default_url = env_url or default_url
    resolved_default_key = env_key or default_key

    if not settings_path.exists():
        save_telemetry_settings(settings_path, resolved_default_url, resolved_default_key)
        return resolved_default_url, resolved_default_key

    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return resolved_default_url, resolved_default_key
        url = str(payload.get("endpoint_url", resolved_default_url)).strip() or resolved_default_url
        key = str(payload.get("api_key", resolved_default_key)).strip() or resolved_default_key
        if env_url:
            url = env_url
        if env_key:
            key = env_key
        return url, key
    except (OSError, json.JSONDecodeError):
        return resolved_default_url, resolved_default_key


def save_telemetry_settings(settings_path: Path, endpoint_url: str, api_key: str) -> None:
    payload = {
        "endpoint_url": endpoint_url.strip(),
        "api_key": api_key.strip(),
    }
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
