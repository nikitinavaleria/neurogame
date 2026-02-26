# Analytics

Папка `analytics/` нужна для оценки качества адаптации после игровых сессий.

Что дает аналитика:
- метрики по каждой сессии (точность, RT, switch cost, fatigue trend), (`analytics/metrics.py`)
- сводку по режимам (`baseline` vs `ppo`), (`analytics/metrics.py`)
- статистическое сравнение режимов (перестановочный тест, p-value). (`analytics/eval_adaptation.py`)

## Запуск 

`pipeline.py`

## Что получаем

При `fetch_from_backend=True`:
- обновляется датасет с сервера:
  - `analytics/data/events.jsonl`
  - `analytics/data/adaptations.jsonl`
  - `analytics/data/sessions.jsonl`

Всегда формируются отчеты:
- `analytics/reports/session_metrics.json` — по каждой сессии,
- `analytics/reports/mode_aggregate.json` — усреднение по режимам,
- `analytics/reports/mode_comparison.json` — baseline vs ppo c p-value.

