# Backend

API для приема телеметрии игры

## Ручки

- `GET /health`
- `POST /v1/events`
- `GET /v1/leaderboard`
- `GET /v1/export/raw`

Ответ на успешный прием всегда:

```json
{"ok": true}
```

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