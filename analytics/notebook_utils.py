from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib import parse, request

import numpy as np
import pandas as pd


def fetch_raw_events(server: str, api_key: str, page_size: int = 1000, max_pages: int = 10000, timeout_sec: float = 20.0) -> list[dict[str, Any]]:
    """
    Скачать сырые события с backend через ручку `/v1/export/raw`.

    Функция постранично запрашивает данные с сервера и возвращает один
    объединённый список словарей. Здесь не выполняется аналитическая
    обработка: задача функции только получить исходные события в том виде,
    в котором их отдаёт backend.

    Параметры:
    - `server`: базовый адрес backend, например `http://127.0.0.1:8000`;
    - `api_key`: ключ доступа к выгрузке;
    - `page_size`: размер одной страницы выгрузки;
    - `max_pages`: защита от бесконечной пагинации;
    - `timeout_sec`: сетевой таймаут для одного запроса.
    """
    rows: list[dict[str, Any]] = []
    offset = 0
    safe_page_size = max(1, min(5000, int(page_size)))
    safe_max_pages = max(1, int(max_pages))
    server = server.rstrip("/")

    for _ in range(safe_max_pages):
        query = parse.urlencode(
            {
                "api_key": api_key,
                "limit": safe_page_size,
                "offset": offset,
            }
        )
        url = f"{server}/v1/export/raw?{query}"
        with request.urlopen(url, timeout=timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
        page_rows = payload.get("rows", [])
        if not isinstance(page_rows, list):
            raise ValueError("Backend returned rows in an unexpected format.")
        page_rows = [row for row in page_rows if isinstance(row, dict)]
        if not page_rows:
            break
        rows.extend(page_rows)
        offset += len(page_rows)
        if len(page_rows) < safe_page_size:
            break
    return rows


def save_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> Path:
    """
    Сохранить список записей в формате JSONL.

    Каждая запись пишется в отдельную строку. Это удобно для промежуточного
    хранения сырых событий и подготовленных выгрузок, потому что такой формат
    легко читать обратно и он хорошо подходит для больших наборов данных.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return target


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """
    Прочитать JSONL-файл и вернуть список словарей.

    Если файл отсутствует, функция не падает с ошибкой, а возвращает пустой
    список. Это удобно для ноутбуков, где пользователь может сначала
    попробовать локальную загрузку, а затем при необходимости скачать данные
    заново с сервера.
    """
    source = Path(path)
    if not source.exists():
        return []
    rows: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _as_dict(value: Any) -> dict[str, Any]:
    """
    Безопасно привести значение к словарю, если это возможно.

    В сырых событиях некоторые поля уже приходят как словари, а некоторые
    могут быть сериализованы в JSON-строку. Эта функция нужна для того,
    чтобы дальше в коде можно было единообразно работать именно со словарями.
    Если преобразование невозможно, возвращается пустой словарь.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def _infer_mode(model_version: Any, payload: dict[str, Any]) -> str:
    """
    Определить режим адаптации для записи.

    Сначала функция пытается взять режим из `payload["mode"]`, потому что
    это наиболее прямой и надёжный источник. Если режима в payload нет,
    используется `model_version`. Если и там нельзя уверенно распознать
    режим, по умолчанию возвращается `baseline`.
    """
    payload_mode = str(payload.get("mode", "")).strip().lower()
    if payload_mode:
        return payload_mode
    model_text = str(model_version or "").lower()
    if "ppo" in model_text or "model" in model_text:
        return "ppo"
    return "baseline"


def rows_to_task_table(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """
    Преобразовать сырые backend-события в плоскую таблицу уровня задач.

    На выходе каждая строка соответствует одной задаче (`task_result`).
    Функция извлекает из сырых событий только те поля, которые реально нужны
    для анализа прохождения: режим, тип задачи, номер батча, уровень,
    правильность ответа, время ответа и служебные признаки вроде `answered`
    и `solved`.

    Эта таблица является базовой для большинства сравнений в разделе 5.1:
    из неё можно считать точность, долю отвеченных задач, время ответа,
    сравнение по типам мини-игр и другие показатели.
    """
    task_rows: list[dict[str, Any]] = []

    for row in rows:
        if row.get("event_type") != "task_result":
            continue
        payload = _as_dict(row.get("payload"))
        nested_payload = _as_dict(payload.get("payload"))
        timestamp = pd.to_datetime(row.get("event_ts"), utc=True, errors="coerce")
        reaction_time = pd.to_numeric(payload.get("reaction_time"), errors="coerce")
        correct = pd.to_numeric(payload.get("correct"), errors="coerce")
        task_rows.append(
            {
                "event_id": row.get("event_id"),
                "event_ts": row.get("event_ts"),
                "event_datetime": timestamp,
                "session_id": str(payload.get("session_id", row.get("session_id", ""))).strip(),
                "account_id": str(payload.get("user_id", row.get("user_id", ""))).strip(),
                "mode": _infer_mode(row.get("model_version"), payload),
                "task_id": payload.get("task_id"),
                "batch_index": pd.to_numeric(payload.get("batch_index"), errors="coerce"),
                "batch_task_index": pd.to_numeric(payload.get("batch_task_index"), errors="coerce"),
                "level": pd.to_numeric(payload.get("level"), errors="coerce"),
                "reaction_time": reaction_time,
                "correct": pd.to_numeric(correct, errors="coerce"),
                "deadline_met": pd.to_numeric(payload.get("deadline_met"), errors="coerce"),
                "answered": 1 if int(payload.get("deadline_met", 0) or 0) == 1 else 0,
                "solved": 1 if int(payload.get("deadline_met", 0) or 0) == 1 and int(payload.get("correct", 0) or 0) == 1 else 0,
                "question_text": nested_payload.get("question_text"),
                "rule": nested_payload.get("rule"),
                "target_symbol": nested_payload.get("target_symbol"),
            }
        )

    df = pd.DataFrame(task_rows)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "event_id",
                "event_ts",
                "event_datetime",
                "session_id",
                "account_id",
                "mode",
                "task_id",
                "batch_index",
                "batch_task_index",
                "level",
                "reaction_time",
                "correct",
                "deadline_met",
                "answered",
                "solved",
                "question_text",
                "rule",
                "target_symbol",
            ]
        )

    df["correct"] = df["correct"].fillna(0).astype(int)
    df["deadline_met"] = df["deadline_met"].fillna(0).astype(int)
    df["answered"] = df["answered"].astype(int)
    df["solved"] = df["solved"].astype(int)
    df = df.sort_values(["session_id", "event_datetime", "batch_task_index"], kind="stable").reset_index(drop=True)
    return df


def rows_to_adaptation_table(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """
    Преобразовать сырые backend-события в таблицу шагов адаптации.

    На выходе каждая строка соответствует одному событию `adaptation_step`.
    В таблицу выносятся:
    - действие модели;
    - изменение темпа;
    - текущее состояние игрока перед адаптацией;
    - награда;
    - смещения сложности по отдельным мини-играм.

    Именно эта таблица нужна для раздела 5.2, где анализируется поведение
    адаптивной модели и её реакция на состояние игрока.
    """
    adaptation_rows: list[dict[str, Any]] = []

    for row in rows:
        if row.get("event_type") != "adaptation_step":
            continue
        payload = _as_dict(row.get("payload"))
        timestamp = pd.to_datetime(row.get("event_ts"), utc=True, errors="coerce")
        state = payload.get("state", [])
        if not isinstance(state, list):
            state = []
        task_offsets = _as_dict(payload.get("task_offsets"))
        adaptation_rows.append(
            {
                "event_id": row.get("event_id"),
                "event_ts": row.get("event_ts"),
                "event_datetime": timestamp,
                "session_id": str(payload.get("session_id", row.get("session_id", ""))).strip(),
                "account_id": str(payload.get("user_id", row.get("user_id", ""))).strip(),
                "mode": _infer_mode(row.get("model_version"), payload),
                "step": pd.to_numeric(payload.get("step"), errors="coerce"),
                "batch_index": pd.to_numeric(payload.get("batch_index"), errors="coerce"),
                "batch_tasks_completed": pd.to_numeric(payload.get("batch_tasks_completed"), errors="coerce"),
                "action_id": pd.to_numeric(payload.get("action_id"), errors="coerce"),
                "delta_level": pd.to_numeric(payload.get("delta_level"), errors="coerce"),
                "delta_tempo": pd.to_numeric(payload.get("delta_tempo"), errors="coerce"),
                "reward": pd.to_numeric(payload.get("reward"), errors="coerce"),
                "level": pd.to_numeric(payload.get("level"), errors="coerce"),
                "tempo_offset": pd.to_numeric(payload.get("tempo_offset"), errors="coerce"),
                "action_space": payload.get("action_space"),
                "state_accuracy": float(state[0]) if len(state) > 0 else np.nan,
                "state_mean_rt": float(state[1]) if len(state) > 1 else np.nan,
                "state_std_rt": float(state[2]) if len(state) > 2 else np.nan,
                "state_error_streak": float(state[3]) if len(state) > 3 else np.nan,
                "state_switch_cost": float(state[4]) if len(state) > 4 else np.nan,
                "state_fatigue_trend": float(state[5]) if len(state) > 5 else np.nan,
                "state_level": float(state[6]) if len(state) > 6 else np.nan,
                "task_offset_compare_codes": pd.to_numeric(task_offsets.get("compare_codes"), errors="coerce"),
                "task_offset_sequence_memory": pd.to_numeric(task_offsets.get("sequence_memory"), errors="coerce"),
                "task_offset_rule_switch": pd.to_numeric(task_offsets.get("rule_switch"), errors="coerce"),
                "task_offset_parity_check": pd.to_numeric(task_offsets.get("parity_check"), errors="coerce"),
                "task_offset_radar_scan": pd.to_numeric(task_offsets.get("radar_scan"), errors="coerce"),
            }
        )

    if not adaptation_rows:
        return pd.DataFrame()

    return pd.DataFrame(adaptation_rows).sort_values(
        ["session_id", "step", "event_datetime"],
        kind="stable",
    ).reset_index(drop=True)


def load_account_map(path: str | Path = "analytics/inputs/account_map.csv") -> pd.DataFrame:
    """
    Загрузить таблицу соответствия аккаунтов и участников из CSV.

    Эта функция оставлена как вспомогательная и как запасной вариант,
    хотя в текущем рабочем процессе соответствия удобнее задавать прямо
    словарём в ноутбуке. Если файл не найден, возвращается пустая таблица.
    """
    source = Path(path)
    if not source.exists():
        return pd.DataFrame(columns=["account_id", "participant_id"])
    mapping = pd.read_csv(source)
    required = {"account_id", "participant_id"}
    missing = required.difference(mapping.columns)
    if missing:
        raise ValueError(f"account_map is missing columns: {sorted(missing)}")
    mapping = mapping.copy()
    mapping["account_id"] = mapping["account_id"].astype(str).str.strip()
    mapping["participant_id"] = mapping["participant_id"].astype(str).str.strip()
    mapping = mapping[mapping["account_id"] != ""]
    return mapping.drop_duplicates(subset=["account_id"], keep="last")


def load_participants(path: str | Path = "analytics/inputs/participants.csv") -> pd.DataFrame:
    """
    Загрузить таблицу метаданных участников из CSV.

    Функция также оставлена как вспомогательная. Она читает возрастные
    группы, возраст в годах и дополнительные комментарии по участникам.
    Если файла нет, возвращается пустая таблица с ожидаемыми колонками.
    """
    source = Path(path)
    if not source.exists():
        return pd.DataFrame(columns=["participant_id", "age_group", "age_years", "comment"])
    participants = pd.read_csv(source)
    if "participant_id" not in participants.columns:
        raise ValueError("participants.csv must contain participant_id.")
    participants = participants.copy()
    participants["participant_id"] = participants["participant_id"].astype(str).str.strip()
    if "age_group" not in participants.columns:
        participants["age_group"] = "unknown"
    participants["age_group"] = participants["age_group"].fillna("unknown").astype(str)
    if "age_years" not in participants.columns:
        participants["age_years"] = np.nan
    if "comment" not in participants.columns:
        participants["comment"] = ""
    return participants.drop_duplicates(subset=["participant_id"], keep="last")


def attach_participant_columns(task_df: pd.DataFrame, account_map: pd.DataFrame | None = None, participants: pd.DataFrame | None = None,) -> pd.DataFrame:
    """
    Подмешать к таблице данные об участниках из отдельных таблиц соответствия.

    Эта функция была полезна для варианта с внешними CSV-файлами. Она
    сопоставляет `account_id` с `participant_id`, а затем добавляет
    возрастные признаки из таблицы участников. В текущем упрощённом workflow
    чаще используется версия со словарями, но функцию полезно сохранить.
    """
    df = task_df.copy()
    if df.empty:
        df["participant_id"] = pd.Series(dtype="object")
        df["age_group"] = pd.Series(dtype="object")
        return df

    if account_map is None:
        account_map = pd.DataFrame(columns=["account_id", "participant_id"])
    if participants is None:
        participants = pd.DataFrame(columns=["participant_id", "age_group", "age_years", "comment"])

    if not account_map.empty:
        df = df.merge(account_map, how="left", on="account_id")
    else:
        df["participant_id"] = np.nan
    df["participant_id"] = df["participant_id"].fillna(df["account_id"])

    if not participants.empty:
        df = df.merge(participants, how="left", on="participant_id")
    else:
        df["age_group"] = "unknown"
        df["age_years"] = np.nan
        df["comment"] = ""

    df["age_group"] = df["age_group"].fillna("unknown")
    return df


def attach_participant_columns_from_dicts(
    df: pd.DataFrame,
    account_to_participant: dict[str, str] | None = None,
    participant_meta: dict[str, dict[str, Any]] | None = None,
) -> pd.DataFrame:
    """
    Подмешать participant_id, возраст и гендер с помощью обычных словарей Python.

    Это основной рабочий вариант для ноутбуков. Он специально сделан
    максимально простым: пользователь может прямо в ноутбуке задать,
    какие аккаунты относятся к одному и тому же человеку, а также указать
    возрастную группу, пол и другие метаданные для каждого участника.

    Функция не меняет исходную таблицу на месте, а возвращает её копию
    с добавленными колонками:
    - `participant_id`
    - `age_group`
    - `gender`
    - `age_years`
    - `comment`
    """
    work = df.copy()
    if work.empty:
        return work

    account_to_participant = account_to_participant or {}
    participant_meta = participant_meta or {}

    work["participant_id"] = work["account_id"].map(account_to_participant).fillna(work["account_id"])
    work["age_group"] = work["participant_id"].map(
        lambda pid: (participant_meta.get(pid, {}) or {}).get("age_group", "unknown")
    )
    work["gender"] = work["participant_id"].map(
        lambda pid: (participant_meta.get(pid, {}) or {}).get("gender", "unknown")
    )
    work["age_years"] = work["participant_id"].map(
        lambda pid: (participant_meta.get(pid, {}) or {}).get("age_years", np.nan)
    )
    work["comment"] = work["participant_id"].map(
        lambda pid: (participant_meta.get(pid, {}) or {}).get("comment", "")
    )
    work["age_group"] = work["age_group"].fillna("unknown")
    work["gender"] = work["gender"].fillna("unknown")
    return work


def build_session_table(task_df: pd.DataFrame) -> pd.DataFrame:
    """
    Собрать из таблицы задач итоговую таблицу сессий.

    На выходе каждая строка соответствует одной игровой сессии. Функция
    агрегирует task-level данные в более крупные метрики:
    - общее число задач;
    - число отвеченных задач;
    - число успешно решённых задач;
    - общую точность;
    - точность по отвеченным задачам;
    - долю отвеченных задач;
    - среднее, медиану и верхний квантиль времени ответа;
    - движение по уровням сложности.

    Эта таблица удобна для сравнения режимов на уровне отдельных сессий.
    """
    if task_df.empty:
        return pd.DataFrame()

    work = task_df.copy().sort_values(["session_id", "event_datetime", "batch_task_index"], kind="stable")
    grouped = []

    for keys, group in work.groupby(
        ["participant_id", "account_id", "session_id", "mode", "age_group", "gender"],
        dropna=False,
        sort=False,
    ):
        participant_id, account_id, session_id, mode, age_group, gender = keys
        answered_mask = group["answered"] == 1
        answered_rts = group.loc[answered_mask, "reaction_time"].dropna()
        levels = group["level"].dropna()
        timestamps = group["event_datetime"].dropna()

        grouped.append(
            {
                "participant_id": participant_id,
                "account_id": account_id,
                "session_id": session_id,
                "mode": mode,
                "age_group": age_group,
                "gender": gender,
                "total_tasks": int(len(group)),
                "answered_tasks": int(group["answered"].sum()),
                "solved_tasks": int(group["solved"].sum()),
                "accuracy_total": float(group["correct"].mean()) if len(group) else np.nan,
                "accuracy_answered": (
                    float(group["solved"].sum() / group["answered"].sum())
                    if int(group["answered"].sum()) > 0
                    else np.nan
                ),
                "answered_rate": float(group["answered"].mean()) if len(group) else np.nan,
                "mean_rt_ms": float(answered_rts.mean()) if not answered_rts.empty else np.nan,
                "median_rt_ms": float(answered_rts.median()) if not answered_rts.empty else np.nan,
                "p90_rt_ms": float(answered_rts.quantile(0.9)) if not answered_rts.empty else np.nan,
                "first_level": int(levels.iloc[0]) if not levels.empty else np.nan,
                "last_level": int(levels.iloc[-1]) if not levels.empty else np.nan,
                "max_level": int(levels.max()) if not levels.empty else np.nan,
                "level_gain": (
                    int(levels.iloc[-1] - levels.iloc[0]) if len(levels) >= 1 else np.nan
                ),
                "completed_batches": int(group["batch_index"].dropna().nunique()),
                "task_span_minutes": (
                    float((timestamps.max() - timestamps.min()).total_seconds() / 60.0)
                    if len(timestamps) >= 2
                    else np.nan
                ),
            }
        )

    return pd.DataFrame(grouped).sort_values(["mode", "participant_id", "session_id"]).reset_index(drop=True)


def build_participant_mode_table(session_df: pd.DataFrame) -> pd.DataFrame:
    """
    Агрегировать метрики сессий внутри каждого участника и режима адаптации.

    На выходе одна строка соответствует одному участнику в одном режиме
    (`baseline` или `ppo`). Это важная таблица для ВКР, потому что она
    уменьшает перекос, возникающий в ситуации, когда одни пользователи
    играли заметно чаще других.

    Здесь рассчитываются усреднённые показатели по сессиям участника, а также
    суммарные значения, например общее число решённых задач.
    """
    if session_df.empty:
        return pd.DataFrame()

    rows = []
    for keys, group in session_df.groupby(["participant_id", "mode", "age_group", "gender"], dropna=False, sort=False):
        participant_id, mode, age_group, gender = keys
        total_tasks = group["total_tasks"].sum()
        answered_tasks = group["answered_tasks"].sum()
        solved_tasks = group["solved_tasks"].sum()
        rows.append(
            {
                "participant_id": participant_id,
                "mode": mode,
                "age_group": age_group,
                "gender": gender,
                "sessions": int(len(group)),
                "total_tasks": int(total_tasks),
                "answered_tasks": int(answered_tasks),
                "solved_tasks": int(solved_tasks),
                "accuracy_total": (
                    float(solved_tasks / total_tasks) if total_tasks > 0 else np.nan
                ),
                "accuracy_answered": (
                    float(solved_tasks / answered_tasks) if answered_tasks > 0 else np.nan
                ),
                "answered_rate": (
                    float(answered_tasks / total_tasks) if total_tasks > 0 else np.nan
                ),
                "mean_rt_ms": float(group["mean_rt_ms"].mean()),
                "median_rt_ms": float(group["median_rt_ms"].mean()),
                "p90_rt_ms": float(group["p90_rt_ms"].mean()),
                "max_level": float(group["max_level"].max()),
                "level_gain_mean": float(group["level_gain"].mean()),
                "solved_tasks_per_session": float(group["solved_tasks"].mean()),
                "answered_tasks_per_session": float(group["answered_tasks"].mean()),
                "total_tasks_per_session": float(group["total_tasks"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["participant_id", "mode"]).reset_index(drop=True)


def mode_summary_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Построить компактную сводную таблицу средних метрик по режимам.

    Функция подходит и для `session_table`, и для `participant_mode_table`.
    Она нужна как быстрый обзор: сколько строк относится к каждому режиму,
    сколько участников представлено в данных и каковы средние значения
    ключевых метрик в `baseline` и `ppo`.
    """
    if df.empty:
        return pd.DataFrame()

    summary_rows = []
    for mode, group in df.groupby("mode", sort=False):
        summary_rows.append(
            {
                "mode": mode,
                "rows": int(len(group)),
                "participants": int(group["participant_id"].nunique()) if "participant_id" in group.columns else np.nan,
                "accuracy_total_mean": float(group["accuracy_total"].mean()),
                "answered_rate_mean": float(group["answered_rate"].mean()),
                "mean_rt_ms_mean": float(group["mean_rt_ms"].mean()),
                "median_rt_ms_mean": float(group["median_rt_ms"].mean()) if "median_rt_ms" in group.columns else np.nan,
                "level_gain_mean": float(group["level_gain"].mean()) if "level_gain" in group.columns else float(group["level_gain_mean"].mean()),
                "solved_tasks_mean": float(group["solved_tasks"].mean()) if "solved_tasks" in group.columns else float(group["solved_tasks_per_session"].mean()),
                "answered_tasks_mean": float(group["answered_tasks"].mean()) if "answered_tasks" in group.columns else float(group["answered_tasks_per_session"].mean()),
                "total_tasks_mean": float(group["total_tasks"].mean()) if "total_tasks" in group.columns else float(group["total_tasks_per_session"].mean()),
            }
        )
    return pd.DataFrame(summary_rows)


def unpaired_permutation_test(
    baseline_values: pd.Series | list[float],
    model_values: pd.Series | list[float],
    higher_is_better: bool = True,
    n_perm: int = 5000,
    seed: int = 42,
) -> dict[str, float]:
    """
    Сравнить две независимые выборки с помощью permutation test.

    Этот тест полезен, когда мы хотим сравнить все наблюдения режима
    `baseline` со всеми наблюдениями режима `ppo`, не предполагая нормальность
    распределения. Функция возвращает:
    - среднее значение в baseline;
    - среднее значение в model;
    - разницу средних (`delta`);
    - p-value.

    Параметр `higher_is_better` задаёт направление интерпретации:
    для точности и числа решённых задач он должен быть `True`,
    а для времени ответа — `False`.
    """
    baseline = pd.Series(baseline_values).dropna().astype(float).to_numpy()
    model = pd.Series(model_values).dropna().astype(float).to_numpy()
    if len(baseline) == 0 or len(model) == 0:
        return {"baseline_mean": np.nan, "model_mean": np.nan, "delta": np.nan, "p_value": np.nan}

    observed = model.mean() - baseline.mean()
    pooled = np.concatenate([baseline, model])
    rng = np.random.default_rng(seed)
    more_extreme = 0
    n_baseline = len(baseline)

    for _ in range(n_perm):
        shuffled = rng.permutation(pooled)
        baseline_perm = shuffled[:n_baseline]
        model_perm = shuffled[n_baseline:]
        diff = model_perm.mean() - baseline_perm.mean()
        if higher_is_better:
            if diff >= observed:
                more_extreme += 1
        else:
            if diff <= observed:
                more_extreme += 1

    return {
        "baseline_mean": float(baseline.mean()),
        "model_mean": float(model.mean()),
        "delta": float(observed),
        "p_value": float((more_extreme + 1) / (n_perm + 1)),
    }


def paired_signflip_test(
    participant_mode_df: pd.DataFrame,
    metric: str,
    higher_is_better: bool = True,
    n_perm: int = 5000,
    seed: int = 42,
) -> dict[str, float]:
    """
    Выполнить парный randomization test для сравнения baseline и ppo у одних и тех же участников.

    Этот тест сильнее непарного сравнения, потому что он рассматривает только
    тех участников, у которых есть данные в обоих режимах. Сначала строятся
    пары значений `baseline` и `ppo` для каждого участника, затем по разностям
    выполняется sign-flip test.

    Функция особенно полезна для главного вывода ВКР: помогает ли модельный
    режим тем же самым людям, а не просто другой группе пользователей.
    """
    if participant_mode_df.empty:
        return {"pairs": 0, "baseline_mean": np.nan, "model_mean": np.nan, "delta": np.nan, "p_value": np.nan}

    pivot = participant_mode_df.pivot_table(index="participant_id", columns="mode", values=metric, aggfunc="mean")
    if "baseline" not in pivot.columns or "ppo" not in pivot.columns:
        return {"pairs": 0, "baseline_mean": np.nan, "model_mean": np.nan, "delta": np.nan, "p_value": np.nan}

    paired = pivot[["baseline", "ppo"]].dropna()
    if paired.empty:
        return {"pairs": 0, "baseline_mean": np.nan, "model_mean": np.nan, "delta": np.nan, "p_value": np.nan}

    baseline = paired["baseline"].to_numpy(dtype=float)
    model = paired["ppo"].to_numpy(dtype=float)
    deltas = model - baseline
    observed = deltas.mean()
    rng = np.random.default_rng(seed)
    more_extreme = 0

    for _ in range(n_perm):
        signs = rng.choice([-1.0, 1.0], size=len(deltas))
        permuted = (deltas * signs).mean()
        if higher_is_better:
            if permuted >= observed:
                more_extreme += 1
        else:
            if permuted <= observed:
                more_extreme += 1

    return {
        "pairs": int(len(paired)),
        "baseline_mean": float(baseline.mean()),
        "model_mean": float(model.mean()),
        "delta": float(observed),
        "p_value": float((more_extreme + 1) / (n_perm + 1)),
    }


def task_mode_summary(task_df: pd.DataFrame) -> pd.DataFrame:
    """
    Построить сводную таблицу по типам задач и режимам адаптации.

    На выходе каждая строка соответствует конкретной мини-игре в конкретном
    режиме. Это позволяет проверить, одинаково ли проявляется эффект модели
    для разных когнитивных задач, или улучшение особенно заметно только
    для части из них.
    """
    if task_df.empty:
        return pd.DataFrame()

    rows = []
    for keys, group in task_df.groupby(["mode", "task_id"], sort=False):
        mode, task_id = keys
        answered_rts = group.loc[group["answered"] == 1, "reaction_time"].dropna()
        rows.append(
            {
                "mode": mode,
                "task_id": task_id,
                "rows": int(len(group)),
                "accuracy_total": float(group["correct"].mean()),
                "answered_rate": float(group["answered"].mean()),
                "solved_rate": float(group["solved"].mean()),
                "mean_rt_ms": float(answered_rts.mean()) if not answered_rts.empty else np.nan,
                "median_rt_ms": float(answered_rts.median()) if not answered_rts.empty else np.nan,
            }
        )
    return pd.DataFrame(rows)


def save_prepared_tables(
    out_dir: str | Path,
    task_df: pd.DataFrame,
    session_df: pd.DataFrame,
    participant_mode_df: pd.DataFrame,
    adaptation_df: pd.DataFrame | None = None,
) -> Path:
    """
    Сохранить все подготовленные аналитические таблицы в одну папку.

    Функция используется в подготовительном ноутбуке после того, как из сырых
    событий уже были собраны таблицы для анализа. На диск записываются:
    - `task_table.csv`
    - `session_table.csv`
    - `participant_mode_table.csv`
    - `adaptation_table.csv` (если она была передана)

    Это позволяет затем открывать ноутбуки 5.1 и 5.2 без повторной
    подготовки данных.
    """
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    task_df.to_csv(target / "task_table.csv", index=False)
    session_df.to_csv(target / "session_table.csv", index=False)
    participant_mode_df.to_csv(target / "participant_mode_table.csv", index=False)
    if adaptation_df is not None:
        adaptation_df.to_csv(target / "adaptation_table.csv", index=False)
    return target
