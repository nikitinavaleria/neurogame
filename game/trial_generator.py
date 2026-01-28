import random

from data.models import TrialSpec, BlockParams
from game.tasks import sample_stimulus, get_correct_action, build_default_mapping


def generate_block(params: BlockParams, seed: int) -> list[TrialSpec]:
    """
    Генерирует список TrialSpec на один блок.

    - длина = params.n_trials
    - задачи берём из params.tasks_enabled
    - переключаем задачу с вероятностью params.switch_rate
    - stimulus и correct_action считаем через game/tasks.py
    """
    rng = random.Random(seed)
    mapping = build_default_mapping()

    trials: list[TrialSpec] = []

    # 1) выбираем первую задачу случайно
    current_task = rng.choice(params.tasks_enabled)

    for i in range(params.n_trials):
        # 2) начиная со 2-го trial — можем переключиться
        if i > 0:
            if len(params.tasks_enabled) >= 2 and rng.random() < params.switch_rate:
                # выбираем любую задачу, кроме текущей
                other_tasks = [t for t in params.tasks_enabled if t != current_task]
                if other_tasks:
                    current_task = rng.choice(other_tasks)

        # 3) генерируем стимул
        stimulus = sample_stimulus(rng, params)

        # 4) правильный ответ
        correct_action = get_correct_action(current_task, stimulus, mapping)

        # 5) is_switch относительно предыдущего
        if i == 0:
            is_switch = False
        else:
            is_switch = (current_task != trials[i - 1].task_id)

        # 6) собираем TrialSpec
        trial = TrialSpec(
            trial_index=i,
            task_id=current_task,
            stimulus=stimulus,
            correct_action=correct_action,
            is_switch=is_switch,
        )

        trials.append(trial)

    return trials
