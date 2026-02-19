# Training Pipeline

Папка `training/` хранит весь pipeline обучения модели.

## Где лежат данные для обучения

- `training/data/events.jsonl`
- `training/data/adaptations.jsonl`
- `training/data/sessions.jsonl`

Ключевой файл для обучения: `training/data/adaptations.jsonl`.

## Быстрый запуск из PyCharm

### Вариант 1: единый pipeline (сервер -> датасет -> обучение)

Запусти `training/pipeline.py` кнопкой Run.

Параметры задаются в `RUN_CONFIG` внутри файла:
- `server`
- `api_key`
- `out_dir` (по умолчанию `training/data`)
- `model_out_path` (по умолчанию `game/assets/models/ppo_agent.pt`)
- `train_mode`, `epochs`, `batch_size`, `gamma`, `lr`
- `skip_train` (если нужен только экспорт датасета)

### Вариант 2: только обучение по готовому датасету

Запусти `training/train.py` кнопкой Run.

По умолчанию:
- данные читаются из `training/data/adaptations.jsonl`
- веса сохраняются в `game/assets/models/ppo_agent.pt`

## Проверка результата

После обучения обновляются:
- `game/assets/models/ppo_agent.pt`
- `game/assets/models/ppo_agent.meta.json`
