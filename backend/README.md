# Neurogame Backend (MVP)

Минимальный API для приема телеметрии игры.

## Что есть

- `GET /health`
- `POST /v1/events`
- `GET /v1/leaderboard?limit=100&min_tasks=30`
- `GET /v1/export/raw?api_key=...&limit=1000&offset=0`

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

## Streamlit leaderboard

Локальный запуск:

```bash
cd backend
streamlit run leaderboard/main.py --server.port 8501
```

Страница: `http://127.0.0.1:8501`

## Docker (API + Streamlit в одном контейнере)

Из корня проекта:

```bash
docker compose up --build
```

После запуска:
- API: `http://127.0.0.1:8000`
- leaderboard UI: `http://127.0.0.1:8501`

## Минимальный запуск на сервере (без сложностей)

1. На сервере клонировать проект и перейти в корень репозитория.
2. Создать `.env` из примера:

```bash
cp .env.server.example .env
```

3. Поставить свой ключ в `.env`:
- `NEUROGAME_API_KEY=...`

4. Запустить:

```bash
docker compose up -d --build
```

Проверка:
- `http://<server-ip>:8000/health`
- `http://<server-ip>:8501`

## Пайплайн обучения из server-данных

Для выгрузки и обучения используй `training/pipeline.py` (запуск из PyCharm).
Параметры задаются в `RUN_CONFIG` внутри файла.
