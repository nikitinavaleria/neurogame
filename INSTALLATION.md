## 1. Требования к среде выполнения

- ОС: `Windows` или `macOS`.
- Python: `3.12`.
- Пакетный менеджер: `pip`.
- Терминал для запуска модулей.
- Сетевой доступ.
- Опционально: `Docker` и `Docker Compose` (для контейнерного запуска).

Зависимости:
- клиент (`requirements.txt`): `pygame`, `numpy`, `torch`;
- backend (`backend/requirements.txt`): `fastapi`, `uvicorn`, `streamlit`.

## 2. Подготовка проекта к запуску

1. Перейти в корневой каталог проекта:
```bash
cd neurogame
```

2. Создать и активировать виртуальное окружение:
```bash
python3.12 -m venv .venv
source .venv/bin/activate      # macOS/Linux
# .venv\Scripts\activate       # Windows
```

3. Установить зависимости:
```bash
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

4. Подготовить конфигурацию backend:
```bash
cp .env.server.example .env
```

5. Проверить и при необходимости задать параметры в `.env`:
- `NEUROGAME_API_KEY`
- `API_PORT`
- `LEADERBOARD_PORT`
- `NEUROGAME_DB_PATH`

6. Требование к ключам доступа:  
Ключ, указанный в backend (`NEUROGAME_API_KEY`), должен совпадать с ключом телеметрии клиента.  
Значения по умолчанию, присутствующие в коде, допускаются только для демонстрационного запуска.

## 3. Запуск серверной части (Backend)

Поддерживаются два режима запуска: локальный и контейнерный.

### 3.1 Локальный запуск (Python)

1. Перейти в каталог backend:
```bash
cd backend
```

2. Задать переменные окружения:
```bash
export NEUROGAME_API_KEY="your_api_key"
export NEUROGAME_DB_PATH="./neurogame/backend/data/events.db"
```

3. Запустить API:
```bash
python main.py
```

4. Проверить доступность API:
```bash
curl http://127.0.0.1:8000/health
```
Ожидаемый ответ:
```json
{"ok": true}
```

5. (Опционально) Запустить лидерборд:
```bash
streamlit run leaderboard/main.py --server.address=127.0.0.1 --server.port=8501
```

### 3.2 Контейнерный запуск (Docker Compose)

1. Запустить контейнер:
```bash
cd neurogame
docker compose up --build -d
```

2. Проверить API:
```bash
curl http://<host>:${API_PORT:-8000}/health
```

3. Проверить лидерборд:  
Открыть в браузере `http://<host>:${LEADERBOARD_PORT:-8501}`.

## 4. Запуск игрового клиента

1. Перейти в корневой каталог проекта:
```bash
cd neurogame
```

2. Запустить клиент:
```bash
python main.py
```

3. Выполнить вход в интерфейсе:
- зарегистрировать пользователя или выполнить авторизацию под существующей учетной записью;
- перейти в меню запуска игровой сессии.

4. Настроить телеметрию:
- в интерфейсе указать URL в формате `http://<host>:8000/v1/events`;
- выполнить проверку соединения кнопкой «Проверить».

5. Запустить сессию:
- выбрать режим адаптации (`baseline` или `model`);
- начать игровую сессию через интерфейс.

6. Проверить передачу данных:
- при доступном backend события отправляются немедленно;
- при недоступном backend события сохраняются в локальной очереди и отправляются после восстановления соединения.

7. Проверить прием событий на backend:
```bash
curl "http://<host>:8000/v1/export/raw?api_key=<YOUR_API_KEY>&limit=5&offset=0"
```
Ожидаемый результат: ответ содержит массив `rows` с событиями игровой сессии.

## 5. Обучение RL-модели

1. Перейти в корневой каталог проекта:
```bash
cd neurogame
```

2. Обновить параметры источника данных в `training/pipeline.py` (конфигурация `RUN_CONFIG`):
- `server` - адрес backend, например `http://127.0.0.1:8000`;
- `api_key` - действующий API-ключ backend;
- `out_dir` - каталог датасетов (`training/data`);
- `model_out_path` - путь сохранения модели (`game/assets/models/ppo_agent.pt`).

3. Запустить полный pipeline (выгрузка данных + обучение):
```bash
python -m training.pipeline
```

4. Проверить формирование датасетов:
- `training/data/events.jsonl`
- `training/data/adaptations.jsonl`
- `training/data/sessions.jsonl`

5. Проверить артефакты модели:
- `game/assets/models/ppo_agent.pt`
- `game/assets/models/ppo_agent.meta.json`


## 6. Аналитическая обработка результатов

1. Перейти в корневой каталог проекта:
```bash
cd neurogame
```

2. При работе с backend проверить параметры в `analytics/pipeline.py` (конфигурация `RUN_CONFIG`):
- `fetch_from_backend` - `True` для выгрузки с сервера;
- `server` - адрес backend;
- `api_key` - действующий API-ключ;
- `dataset_dir` - каталог датасета (`analytics/data`);
- `reports_dir` - каталог отчетов (`analytics/reports`).

3. Запустить pipeline аналитики:
```bash
python -m analytics.pipeline
```

4. Проверить сформированные отчеты:
- `analytics/reports/session_metrics.json`
- `analytics/reports/mode_aggregate.json`
- `analytics/reports/mode_comparison.json`

5. Назначение выходных файлов:
- `session_metrics.json` - метрики по каждой сессии;
- `mode_aggregate.json` - агрегирование метрик по режимам (`baseline`, `model`);
- `mode_comparison.json` - сравнительный отчет `baseline` vs `model` с p-value.

6. Условие корректной аналитики:  
Файл `analytics/data/events.jsonl` должен содержать события `task_result`; при отсутствии данных pipeline завершится с сообщением об ошибке.

   
## 7. Сборка дистрибутива

1. В репозитории настроен workflow:
- `.github/workflows/build-release.yml`.

2. Триггер workflow:
- ручной запуск (`workflow_dispatch`).

3. Состав CI-сборки:
- `build-macos`: сборка приложения и DMG;
- `build-windows`: сборка `.exe` и инсталлятора Inno Setup.

4. Публикуемые артефакты:
- macOS: `NeuroGame`, `NeuroGame.app`, `NeuroGame.dmg`, `neurogame-*.zip`;
- Windows: `NeuroGame.exe`, `NeuroGameSetup.exe`, `neurogame-*.zip`.
