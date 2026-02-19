import base64
import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, Tuple


USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,24}$")


class UserAuthStore:
    def __init__(self, path: str = "data/users.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({"users": {}})

    def register(self, username: str, password: str) -> Tuple[bool, str, str]:
        username = username.strip()
        if not USERNAME_RE.match(username):
            return False, "Логин: 3-24 символа (буквы, цифры, _.-)", ""
        if len(password) < 4:
            return False, "Пароль слишком короткий (минимум 4 символа)", ""

        user_id = username.lower()
        data = self._load()
        users = data.setdefault("users", {})
        if user_id in users:
            return False, "Пользователь уже существует", ""

        salt = os.urandom(16)
        pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
        users[user_id] = {
            "username": username,
            "salt_b64": base64.b64encode(salt).decode("ascii"),
            "pwd_hash_b64": base64.b64encode(pwd_hash).decode("ascii"),
            "created_at": int(time.time()),
            "stats": {"total_planets": 0},
        }
        self._save(data)
        return True, "Пользователь создан", user_id

    def authenticate(self, username: str, password: str) -> Tuple[bool, str, str]:
        user_id = username.strip().lower()
        data = self._load()
        user = data.get("users", {}).get(user_id)
        if not user:
            return False, "Пользователь не найден", ""

        try:
            salt = base64.b64decode(user["salt_b64"])
            expected = base64.b64decode(user["pwd_hash_b64"])
        except Exception:
            return False, "Поврежденные данные пользователя", ""

        got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
        if not hmac.compare_digest(got, expected):
            return False, "Неверный пароль", ""
        return True, "Успешный вход", user_id

    def get_user_stat(self, user_id: str, key: str, default: float = 0.0) -> float:
        data = self._load()
        user = data.get("users", {}).get(user_id, {})
        stats = user.get("stats", {})
        if not isinstance(stats, dict):
            return default
        value = stats.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def increment_user_stat(self, user_id: str, key: str, delta: float = 1.0) -> float:
        data = self._load()
        users = data.setdefault("users", {})
        user = users.get(user_id)
        if not isinstance(user, dict):
            return 0.0
        stats = user.setdefault("stats", {})
        if not isinstance(stats, dict):
            stats = {}
            user["stats"] = stats
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
