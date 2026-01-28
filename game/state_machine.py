from typing import Optional, Tuple

from data.models import TrialSpec, TrialEvent, BlockParams


# Мы будем хранить фазу trial-а как строку (это проще всего понимать)
PHASE_CUE = "CUE"          # показываем подсказку правила (COLOR/SHAPE)
PHASE_WAIT = "WAIT"        # ждём нажатие кнопки
PHASE_FEEDBACK = "FEEDBACK"  # показываем "Correct/Incorrect"
PHASE_ITI = "ITI"          # маленькая пауза между trial-ами


class TrialStateMachine:
    """
    Это маленький "мозг", который управляет одним trial-ом.

    Идея:
    - trial идёт по фазам (CUE -> WAIT -> FEEDBACK -> ITI)
    - update() вызывается каждый кадр
    - когда trial заканчивается, update() возвращает TrialEvent
    """

    def __init__(self, params: BlockParams):
        # params содержит тайминги (cue_ms, time_limit_ms, feedback_ms, iti_ms)
        self.params = params

        # текущий trial (TrialSpec), который мы проигрываем
        self.trial: Optional[TrialSpec] = None

        # какая сейчас фаза
        self.phase: str = PHASE_CUE

        # когда началась текущая фаза (в миллисекундах)
        self.phase_started_at_ms: int = 0

        # когда мы начали ждать ответ (нужно, чтобы считать RT)
        self.wait_started_at_ms: Optional[int] = None

        # что нажал игрок ("F"/"J"/"K"/"L") или None
        self.response_action: Optional[str] = None

        # время реакции в мс (если ответ был)
        self.rt_ms: Optional[int] = None

        # был ли таймаут
        self.is_timeout: bool = False

        # был ли ответ правильным (True/False), узнаём при ответе или таймауте
        self.is_correct: bool = False

    def start_trial(self, trial: TrialSpec, now_ms: int) -> None:
        """
        Начинаем новый trial.

        now_ms — текущее время (в мс), его даёт сцена/главный цикл игры.
        """
        self.trial = trial

        # Сбрасываем всё состояние trial-а
        self.phase = PHASE_CUE
        self.phase_started_at_ms = now_ms

        self.wait_started_at_ms = None
        self.response_action = None
        self.rt_ms = None
        self.is_timeout = False
        self.is_correct = False

    def get_phase(self) -> str:
        """Сцена/рендерер могут спрашивать фазу, чтобы понимать что рисовать."""
        return self.phase

    def update(self, now_ms: int, action: Optional[str]) -> Tuple[bool, Optional[TrialEvent]]:
        """
        Вызывается КАЖДЫЙ кадр.

        action — это либо "F"/"J"/"K"/"L", либо None (если игрок ничего не нажал).

        Возвращает:
        - finished: True если trial завершился
        - event: TrialEvent если завершился, иначе None
        """
        # Если trial не запущен — просто ничего не делаем
        if self.trial is None:
            return False, None

        # --------------------------
        # 1) ФАЗА: CUE
        # --------------------------
        if self.phase == PHASE_CUE:
            # Мы просто ждём, пока пройдёт cue_ms
            if now_ms - self.phase_started_at_ms >= self.params.cue_ms:
                # Переходим в WAIT (ожидание ответа)
                self.phase = PHASE_WAIT
                self.phase_started_at_ms = now_ms

                # Запоминаем момент начала ожидания — с него считаем RT
                self.wait_started_at_ms = now_ms

            return False, None

        # --------------------------
        # 2) ФАЗА: WAIT
        # --------------------------
        if self.phase == PHASE_WAIT:
            # A) Если игрок нажал кнопку
            if action is not None and self.response_action is None:
                self.response_action = action

                # RT = сейчас - момент начала ожидания
                start = self.wait_started_at_ms if self.wait_started_at_ms is not None else now_ms
                self.rt_ms = now_ms - start

                # Правильность: сравниваем с trial.correct_action
                self.is_correct = (self.response_action == self.trial.correct_action)
                self.is_timeout = False

                # Переходим в FEEDBACK
                self.phase = PHASE_FEEDBACK
                self.phase_started_at_ms = now_ms

                return False, None

            # B) Если ответа нет — проверяем таймаут
            start = self.wait_started_at_ms if self.wait_started_at_ms is not None else now_ms
            if now_ms - start >= self.params.time_limit_ms:
                # Таймаут: ответа нет
                self.response_action = None
                self.rt_ms = None
                self.is_timeout = True
                self.is_correct = False

                # Переходим в FEEDBACK
                self.phase = PHASE_FEEDBACK
                self.phase_started_at_ms = now_ms

                return False, None

            return False, None

        # --------------------------
        # 3) ФАЗА: FEEDBACK
        # --------------------------
        if self.phase == PHASE_FEEDBACK:
            # Здесь мы просто держим экран с "Correct/Incorrect"
            if now_ms - self.phase_started_at_ms >= self.params.feedback_ms:
                self.phase = PHASE_ITI
                self.phase_started_at_ms = now_ms

            return False, None

        # --------------------------
        # 4) ФАЗА: ITI
        # --------------------------
        if self.phase == PHASE_ITI:
            # Маленькая пауза между trial-ами
            if now_ms - self.phase_started_at_ms >= self.params.iti_ms:
                # Trial полностью закончился — собираем TrialEvent
                event = TrialEvent(
                    trial_index=self.trial.trial_index,
                    task_id=self.trial.task_id,
                    is_switch=self.trial.is_switch,
                    correct_action=self.trial.correct_action,
                    response_action=self.response_action,
                    is_correct=self.is_correct,
                    rt_ms=self.rt_ms,
                    is_timeout=self.is_timeout,
                )

                # Сообщаем наружу: trial завершён
                return True, event

            return False, None

        # Если фаза вдруг неизвестная — это ошибка в коде
        raise ValueError(f"Unknown phase: {self.phase}")
