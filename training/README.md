# Training

Папка для обучения модели

## Данные для обучения

- `training/data/events.jsonl`
- `training/data/adaptations.jsonl`
- `training/data/sessions.jsonl`

Ключевой файл для обучения: `training/data/adaptations.jsonl`.

## Запуск 

### Вариант 1 (сервер -> датасет -> обучение)

`pipeline.py`


### Вариант 2 (только обучение по готовому датасету)

`train.py`

## Текущий алгоритм

- Offline Q-learning с CQL-регуляризацией для темпа `[-1, 0, +1]`.
- Дополнительно обучаются multi-head действия по мини-играм:
  - `compare_codes`
  - `sequence_memory`
  - `rule_switch`
  - `parity_check`
  - `radar_scan`
- Итоговый `action_space`: `tempo3_task_offsets_v1`.

Пример обучения только по baseline-логам:

```bash
python -m training.train --data training/data/adaptations.jsonl --mode baseline
```
