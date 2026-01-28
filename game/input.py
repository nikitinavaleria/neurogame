import pygame
from typing import Optional


class InputManager:
    """
    InputManager — это прослойка между pygame и нашей логикой.

    Идея:
    - pygame шлёт события (event)
    - мы смотрим только на KEYDOWN (нажатие)
    - если нажата нужная клавиша -> запоминаем действие ("F"/"J"/"K"/"L")
    - Scene / StateMachine в каждом кадре спрашивают poll_action()
    """

    def __init__(self):
        # Здесь храним "последнее нажатие", которое ещё не было забрано через poll_action()
        self._last_action: Optional[str] = None

        # Mapping клавиш pygame -> наши действия
        # Можно легко менять раскладку здесь
        self.key_to_action = {
            pygame.K_f: "F",
            pygame.K_j: "J",
            pygame.K_k: "K",
            pygame.K_l: "L",
        }

    def process_pygame_event(self, event) -> None:
        """
        Кормим сюда события pygame из main/scene.

        Мы реагируем только на KEYDOWN.
        """
        if event.type != pygame.KEYDOWN:
            return

        # Берём код клавиши
        key = event.key

        # Если это одна из "игровых" клавиш — запоминаем действие
        if key in self.key_to_action:
            # Важно: если игрок нажал несколько раз быстро,
            # мы сохраняем только последнее (в рамках простого MVP).
            self._last_action = self.key_to_action[key]

    def poll_action(self) -> Optional[str]:
        """
        Возвращает действие ("F"/"J"/"K"/"L"), если оно было нажато.

        Важно: после того как действие возвращено — мы очищаем _last_action,
        чтобы оно не "залипало" и не возвращалось снова на следующем кадре.
        """
        action = self._last_action
        self._last_action = None
        return action

    def reset(self) -> None:
        """
        Явно сбрасывает ввод.
        Полезно вызывать:
        - перед стартом нового trial-а
        - при переходах между сценами
        """
        self._last_action = None
