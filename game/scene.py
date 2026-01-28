import pygame
from typing import Callable, List, Optional

from data.models import BlockParams, TrialEvent, TrialSpec
from game.trial_generator import generate_block
from game.state_machine import (
    TrialStateMachine,
    PHASE_CUE,
    PHASE_WAIT,
    PHASE_FEEDBACK,
    PHASE_ITI,
)
from game.input import InputManager
from game.renderer import Renderer


class GameScene:
    """
    GameScene = "один блок игры".

    Она объединяет:
    - генерацию trials (trial_generator)
    - управление фазами trial-а (state_machine)
    - ввод (input)
    - отрисовку (renderer)

    В main.py ты создашь сцену и будешь:
    - прокидывать ей события pygame
    - вызывать update() каждый кадр
    """

    def __init__(
        self,
        screen: pygame.Surface,
        renderer: Renderer,
        input_manager: InputManager,
        block_params: BlockParams,
        seed: int,
        on_trial_event: Optional[Callable[[TrialEvent], None]] = None,
    ):
        self.screen = screen
        self.renderer = renderer
        self.input = input_manager
        self.params = block_params
        self.seed = seed
        self.on_trial_event = on_trial_event

        # trials и результаты
        self.trials: List[TrialSpec] = []
        self.results: List[TrialEvent] = []

        # индекс текущего trial-а
        self.current_index: int = 0

        # state machine для одного trial-а
        self.sm = TrialStateMachine(self.params)

        # текущее время (мс) — будем обновлять через pygame.time.get_ticks()
        self._started: bool = False
        self._finished: bool = False

        # "очки" для HUD (можно убрать, если не нужно)
        self.score: int = 0

        # Для вывода фидбека: мы будем хранить текст и правильность,
        # чтобы renderer мог это показать во время FEEDBACK-фазы.
        self._feedback_message: Optional[str] = None
        self._feedback_is_correct: Optional[bool] = None

    def start(self) -> None:
        """
        Запуск блока:
        - генерируем список TrialSpec
        - стартуем первый trial в state_machine
        """
        self.trials = generate_block(self.params, seed=self.seed)
        self.results = []
        self.current_index = 0
        self.score = 0
        self._finished = False

        now_ms = pygame.time.get_ticks()

        # стартуем первый trial, если он есть
        if len(self.trials) > 0:
            self.input.reset()
            self.sm.start_trial(self.trials[0], now_ms)
            self._started = True
        else:
            self._finished = True
            self._started = True

    def handle_event(self, event) -> None:
        """
        Сюда main.py передаёт pygame события (KEYDOWN и т.д.)
        Мы отдаём их InputManager-у.
        """
        self.input.process_pygame_event(event)

    def update(self, dt_ms: int = 0) -> None:
        """
        Вызывается каждый кадр.

        dt_ms можно не использовать (в pygame часто удобнее брать ticks),
        но оставлено для совместимости и расширения.
        """
        if not self._started or self._finished:
            return

        now_ms = pygame.time.get_ticks()

        # 1) Получаем действие игрока (если он нажал F/J/K/L)
        action = self.input.poll_action()

        # 2) Обновляем state machine
        finished, event = self.sm.update(now_ms, action)

        # 3) Если trial завершился — сохраняем результат и запускаем следующий trial
        if finished and event is not None:
            self.results.append(event)

            # обновляем "очки" (просто пример)
            if event.is_correct:
                self.score += 1

            # callback наружу (если нужно логировать по ходу)
            if self.on_trial_event is not None:
                self.on_trial_event(event)

            # Переходим к следующему trial
            self.current_index += 1

            if self.current_index >= len(self.trials):
                # блок закончился
                self._finished = True
            else:
                # запускаем следующий trial
                self.input.reset()
                self.sm.start_trial(self.trials[self.current_index], now_ms)

        # 4) РЕНДЕРИНГ (рисуем то, что соответствует текущей фазе)
        self._render()

    def _render(self) -> None:
        """
        Рисуем текущий кадр в зависимости от фазы state_machine.
        """
        if self.sm.trial is None:
            return

        phase = self.sm.get_phase()
        trial = self.sm.trial

        self.renderer.clear()

        # HUD всегда
        self.renderer.draw_hud(
            block_progress=(min(self.current_index + 1, len(self.trials)), len(self.trials)),
            score=self.score,
        )

        # Cue обычно показываем всегда (и в WAIT, и в FEEDBACK тоже можно)
        self.renderer.draw_cue(trial.task_id)

        if phase == PHASE_CUE:
            # В этой фазе мы только показываем cue
            pass

        elif phase == PHASE_WAIT:
            # Показываем cue + стимул, ждём ответ
            self.renderer.draw_stimulus(trial.stimulus)

        elif phase == PHASE_FEEDBACK:
            # Во время feedback хотим показать и стимул (можно убрать) + текст результата
            self.renderer.draw_stimulus(trial.stimulus)

            # В state_machine есть итоговые поля is_correct / is_timeout
            if self.sm.is_timeout:
                self.renderer.draw_feedback(is_correct=False, message="Too slow")
            else:
                self.renderer.draw_feedback(is_correct=self.sm.is_correct)

        elif phase == PHASE_ITI:
            # Пауза — можно просто ничего не рисовать кроме HUD и cue
            pass

        self.renderer.present()

    def is_finished(self) -> bool:
        return self._finished

    def get_results(self) -> List[TrialEvent]:
        return self.results
