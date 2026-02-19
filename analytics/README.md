# Analytics

Папка `analytics/` нужна для оценки качества адаптации после игровых сессий.

Что дает аналитика:
- метрики по каждой сессии (точность, RT, switch cost, fatigue trend),
- сводку по режимам (`baseline` vs `ppo`),
- статистическое сравнение режимов (перестановочный тест, p-value).

## Рекомендуемый запуск (из PyCharm)

Запусти файл: `analytics/pipeline.py`.

Параметры задаются в `RUN_CONFIG`:
- `fetch_from_backend`: сначала подтянуть свежие данные с backend (`/v1/export/raw`),
- `server`, `api_key`: доступ к backend,
- `dataset_dir`: куда класть JSONL датасет (по умолчанию `analytics/data`),
- `reports_dir`: куда сохранить отчеты (по умолчанию `analytics/reports`).

## Что формируется

При `fetch_from_backend=True`:
- обновляется датасет:
  - `analytics/data/events.jsonl`
  - `analytics/data/adaptations.jsonl`
  - `analytics/data/sessions.jsonl`

Всегда формируются отчеты:
- `analytics/reports/session_metrics.json` — по каждой сессии,
- `analytics/reports/mode_aggregate.json` — усреднение по режимам,
- `analytics/reports/mode_comparison.json` — baseline vs ppo c p-value.

## Отдельные скрипты

- `analytics/metrics.py` — печатает метрики по сессиям и агрегат по режимам.
- `analytics/eval_adaptation.py` — печатает сравнение baseline vs ppo.
