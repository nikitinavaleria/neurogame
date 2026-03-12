import json
import re
from pathlib import Path
from typing import Dict, Tuple
from urllib import error, request
from urllib.parse import urlparse


USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,24}$")


class UserAuthStore:
    def __init__(self, path: str = "data/users.json", endpoint_url: str = "", api_key: str = "") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({"stats": {}})
        self.endpoint_url = endpoint_url.strip()
        self.api_key = api_key.strip()

    def set_backend(self, endpoint_url: str, api_key: str) -> None:
        self.endpoint_url = endpoint_url.strip()
        self.api_key = api_key.strip()

    def register(self, username: str, password: str) -> Tuple[bool, str, str]:
        username = username.strip()
        if not USERNAME_RE.match(username):
            return False, "Логин: 3-24 символа (буквы, цифры, _.-)", ""
        if len(password) < 4:
            return False, "Пароль слишком короткий (минимум 4 символа)", ""
        ok, detail, user_id = self._auth_request("/v1/auth/register", username, password)
        if ok:
            return True, "Пользователь создан", user_id
        return False, self._register_message(detail), ""

    def authenticate(self, username: str, password: str) -> Tuple[bool, str, str]:
        ok, detail, user_id = self._auth_request("/v1/auth/login", username.strip(), password)
        if ok:
            return True, "Успешный вход", user_id
        return False, self._login_message(detail), ""

    def get_user_stat(self, user_id: str, key: str, default: float = 0.0) -> float:
        data = self._load()
        stats_root = data.get("stats", {})
        if isinstance(stats_root, dict):
            stats = stats_root.get(user_id, {})
        else:
            stats = {}
        if not isinstance(stats, dict):
            stats = {}
        if not stats:
            # Совместимость со старым форматом users.json
            user = data.get("users", {}).get(user_id, {})
            stats = user.get("stats", {}) if isinstance(user, dict) else {}
        if not isinstance(stats, dict):
            return default
        value = stats.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def increment_user_stat(self, user_id: str, key: str, delta: float = 1.0) -> float:
        data = self._load()
        stats_root = data.setdefault("stats", {})
        if not isinstance(stats_root, dict):
            stats_root = {}
            data["stats"] = stats_root
        stats = stats_root.setdefault(user_id, {})
        if not isinstance(stats, dict):
            stats = {}
            stats_root[user_id] = stats
        try:
            current = float(stats.get(key, 0.0))
        except (TypeError, ValueError):
            current = 0.0
        new_value = current + float(delta)
        stats[key] = new_value
        self._save(data)
        return new_value

    def _load(self) -> Dict:
        with self.path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: Dict) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _auth_request(self, path: str, username: str, password: str) -> tuple[bool, str, str]:
        if not self.api_key:
            return False, "missing_api_key", ""
        endpoint = self._auth_endpoint(path)
        if not endpoint:
            return False, "invalid_auth_endpoint", ""
        body = {
            "api_key": self.api_key,
            "username": username,
            "password": password,
        }
        req = request.Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=4.0) as resp:
                if resp.status != 200:
                    return False, f"http_{resp.status}", ""
                payload = json.loads((resp.read().decode("utf-8") or "{}"))
                if not isinstance(payload, dict) or payload.get("ok") is not True:
                    return False, "invalid_server_response", ""
                user_id = str(payload.get("user_id", "")).strip()
                if not user_id:
                    return False, "invalid_server_response", ""
                return True, "ok", user_id
        except error.HTTPError as exc:
            detail = self._read_error_detail(exc)
            if detail:
                return False, detail, ""
            return False, f"http_{exc.code}", ""
        except (error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return False, "connection_error", ""

    def _auth_endpoint(self, path: str) -> str:
        parsed = urlparse(self.endpoint_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return ""
        base = f"{parsed.scheme}://{parsed.netloc}"
        return f"{base}{path}"

    @staticmethod
    def _read_error_detail(exc: error.HTTPError) -> str:
        try:
            raw = exc.read().decode("utf-8") or "{}"
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return str(payload.get("detail", "")).strip()
        except (OSError, json.JSONDecodeError):
            return ""
        return ""

    @staticmethod
    def _register_message(detail: str) -> str:
        mapping = {
            "username_required": "Заполни логин",
            "username_invalid_length": "Логин: 3-24 символа",
            "username_invalid_chars": "Логин: используйте буквы, цифры, _.-",
            "password_too_short": "Пароль слишком короткий (минимум 4 символа)",
            "user_exists": "Пользователь уже существует",
            "invalid_api_key": "Неверный API-ключ. Обратитесь к специалисту.",
            "missing_api_key": "Не настроен API-ключ подключения",
            "invalid_auth_endpoint": "Некорректный адрес сервера авторизации",
            "connection_error": "Нет связи с сервером авторизации",
        }
        return mapping.get(detail, "Ошибка регистрации")

    @staticmethod
    def _login_message(detail: str) -> str:
        mapping = {
            "username_required": "Заполни логин",
            "user_not_found": "Пользователь не найден",
            "invalid_password": "Неверный пароль",
            "invalid_api_key": "Неверный API-ключ. Обратитесь к специалисту.",
            "missing_api_key": "Не настроен API-ключ подключения",
            "invalid_auth_endpoint": "Некорректный адрес сервера авторизации",
            "connection_error": "Нет связи с сервером авторизации",
        }
        return mapping.get(detail, "Ошибка входа")
