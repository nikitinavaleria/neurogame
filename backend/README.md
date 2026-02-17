# Neurogame Backend (MVP)

Минимальный API для приема телеметрии игры.

## Что есть

- `GET /health`
- `POST /v1/events`

Ответ на успешный прием всегда:

```json
{"ok": true}
```

## Быстрый запуск

```bash
cd backend
pip install -r requirements.txt
export NEUROGAME_API_KEY="replace-me"
uvicorn main:app --host 0.0.0.0 --port 8000
```

Для PyCharm можно просто запускать файл `backend/main.py` кнопкой Run:
- по умолчанию поднимается `http://127.0.0.1:8000`
- ключ по умолчанию: `dev-key-change-me`

## Переменные окружения

- `NEUROGAME_API_KEY` - ключ для приема событий.
- `NEUROGAME_DB_PATH` - путь к SQLite (по умолчанию `backend/data/events.db`).

Для клиента игры:

- `NEUROGAME_TELEMETRY_URL` - полный URL на ingest endpoint, например `http://127.0.0.1:8000/v1/events`.
- `NEUROGAME_TELEMETRY_API_KEY` - тот же ключ, что и у backend (`NEUROGAME_API_KEY`).
- `NEUROGAME_CLIENT_VERSION` - версия клиента (строка, опционально).

В текущем коде игры уже стоят локальные дефолты:
- URL: `http://127.0.0.1:8000/v1/events`
- API key: `dev-key-change-me`

То есть `main.py` игры тоже можно запускать кнопкой Run без переменных окружения.

## Формат запроса

```json
{
  "api_key": "replace-me",
  "client_version": "1.0.0",
  "events": [
    {
      "event_id": "01HX...",
      "event_type": "task_result",
      "event_ts": "2026-02-17T12:05:11Z",
      "user_id": "u_42",
      "session_id": "s_20260217_120000_u_42",
      "model_version": "baseline_v1",
      "payload": {"correct": true, "rt_ms": 1260}
    }
  ]
}
```

`event_id` идемпотентный: дубликаты тихо игнорируются.

## Мост в текущий формат обучения

Чтобы использовать текущий пайплайн (`data/events.jsonl`, `data/adaptations.jsonl`, `data/sessions.jsonl`), есть скрипт-экспортер:

```bash
python backend/scripts/export_bridge.py \
  --db backend/data/events.db \
  --events-out data/events.jsonl \
  --adaptations-out data/adaptations.jsonl \
  --sessions-out data/sessions.jsonl
```

Скрипт можно запускать кнопкой Run без аргументов: у него дефолтные абсолютные пути по проекту.

Скрипт экспортирует:
- `event_type=task_result` -> `data/events.jsonl`
- `event_type=adaptation_step` -> `data/adaptations.jsonl`
- `event_type=session_end` и `event_type=session_end_partial` -> `data/sessions.jsonl`
