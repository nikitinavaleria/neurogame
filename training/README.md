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

- Offline Q-learning с CQL-регуляризацией для дискретного темпового действия `[-1, 0, +1]`.
- Модель учится максимизировать награду по логам, а не просто копировать baseline-выбор.

Пример обучения только по baseline-логам:

```bash
python -m training.train --data training/data/adaptations.jsonl --mode baseline
```

