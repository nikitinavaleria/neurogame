# Analytics



## Новый рекомендуемый workflow

1. Открыть ноутбук:
   - `analytics/00_prepare_data.ipynb`

2. Внутри ноутбука задать обычные словари:
   - `account_to_participant`
   - `participant_meta`

3. Скачать сырые события прямо с сервера и собрать удобные таблицы:
   - `raw_events.jsonl`
   - `task_table.csv`
   - `adaptation_table.csv`
   - `session_table.csv`
   - `participant_mode_table.csv`

4. Открыть аналитические ноутбуки:
   - `analytics/05_1_compare_modes.ipynb`
   - `analytics/05_2_model_behavior.ipynb`

## Что делает helper-модуль

Файл `analytics/notebook_utils.py` оставляет только простые функции:
- скачать raw events с backend;
- превратить raw events в task-level таблицу;
- превратить raw events в adaptation-level таблицу;
- объединить несколько аккаунтов одного участника;
- подмешать возраст и гендер;
- собрать session-level и participant-level таблицы;
- посчитать простые permutation/sign-flip тесты.


