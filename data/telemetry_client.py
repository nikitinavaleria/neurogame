import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import urlparse


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TelemetryClient:
    def __init__(
        self,
        endpoint_url: str,
        api_key: str,
        client_version: str = "game-dev",
        queue_path: str = "data/telemetry_queue.jsonl",
        max_batch_size: int = 100,
        flush_interval_sec: float = 5.0,
        timeout_sec: float = 2.5,
    ) -> None:
        self.endpoint_url = endpoint_url.strip()
        self.api_key = api_key.strip()
        self.client_version = client_version
        self.max_batch_size = max(1, max_batch_size)
        self.flush_interval_sec = max(0.1, flush_interval_sec)
        self.timeout_sec = max(0.5, timeout_sec)
        self.enabled = bool(self.endpoint_url and self.api_key)
        self.queue_path = Path(queue_path)
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        self.queue: list[dict[str, Any]] = self._load_queue()
        self.last_flush_ts: float = 0.0
        self.last_error: str = ""
        self.last_success_ts: float = 0.0

    def track(
        self,
        event_type: str,
        user_id: str | None,
        session_id: str | None,
        payload: dict[str, Any],
        model_version: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        if not user_id or not session_id:
            return
        event = {
            "event_id": uuid.uuid4().hex,
            "event_type": event_type,
            "event_ts": _utc_now_iso(),
            "user_id": user_id,
            "session_id": session_id,
            "model_version": model_version or "",
            "payload": payload,
        }
        self.queue.append(event)
        self._save_queue()
        self.flush()

    def flush(self, force: bool = False) -> None:
        if not self.enabled or not self.queue:
            return
        now = time.time()
        if not force and (now - self.last_flush_ts) < self.flush_interval_sec:
            return
        self.last_flush_ts = now
        batch = self.queue[: self.max_batch_size]
        body = {
            "api_key": self.api_key,
            "client_version": self.client_version,
            "sent_at": _utc_now_iso(),
            "events": batch,
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.endpoint_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_sec) as resp:
                if resp.status != 200:
                    return
                raw = resp.read().decode("utf-8") or "{}"
                data = json.loads(raw)
                if not isinstance(data, dict) or data.get("ok") is not True:
                    self.last_error = "invalid_server_response"
                    return
        except (error.URLError, error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
            self.last_error = "connection_error"
            return

        self.queue = self.queue[len(batch) :]
        self.last_error = ""
        self.last_success_ts = time.time()
        self._save_queue()
        if self.queue and force:
            self.flush(force=True)

    @staticmethod
    def is_valid_endpoint(url: str) -> bool:
        parsed = urlparse((url or "").strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    def set_endpoint(self, endpoint_url: str) -> None:
        self.endpoint_url = endpoint_url.strip()
        self.enabled = bool(self.endpoint_url and self.api_key)

    def set_api_key(self, api_key: str) -> None:
        self.api_key = api_key.strip()
        self.enabled = bool(self.endpoint_url and self.api_key)

    def queue_size(self) -> int:
        return len(self.queue)

    def check_connection(self) -> tuple[bool, str]:
        if not self.enabled:
            self.last_error = "disabled"
            return False, "Телеметрия выключена (нет адреса или ключа)"
        if not self.is_valid_endpoint(self.endpoint_url):
            self.last_error = "invalid_url"
            return False, "Неверный адрес сервера"

        health_url = self.endpoint_url
        if "/v1/events" in health_url:
            health_url = health_url.replace("/v1/events", "/health")
        elif health_url.endswith("/"):
            health_url = f"{health_url}health"
        else:
            health_url = f"{health_url}/health"

        req = request.Request(health_url, method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout_sec) as resp:
                if resp.status != 200:
                    self.last_error = "health_status_error"
                    return False, "Сервер недоступен"
                raw = resp.read().decode("utf-8") or "{}"
                payload = json.loads(raw)
                if isinstance(payload, dict) and payload.get("ok") is True:
                    self.last_error = ""
                    self.last_success_ts = time.time()
                    return True, "Подключение подтверждено"
                self.last_error = "health_payload_error"
                return False, "Сервер ответил некорректно"
        except (error.URLError, error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
            self.last_error = "connection_error"
            return False, "Нет связи с сервером"

    def _load_queue(self) -> list[dict[str, Any]]:
        if not self.queue_path.exists():
            return []
        events: list[dict[str, Any]] = []
        try:
            with self.queue_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    if isinstance(rec, dict):
                        events.append(rec)
        except (OSError, json.JSONDecodeError):
            return []
        return events

    def _save_queue(self) -> None:
        if not self.queue:
            try:
                self.queue_path.unlink(missing_ok=True)
            except OSError:
                pass
            return
        tmp = self.queue_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for item in self.queue:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        tmp.replace(self.queue_path)
