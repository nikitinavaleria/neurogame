import pygame
from typing import Optional, Tuple


class Renderer:
    """
    Renderer отвечает ТОЛЬКО за рисование.
    Он не считает RT, не решает правильность, не управляет фазами.
    Ему дают данные — он их рисует.
    """

    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.w, self.h = screen.get_size()

        # Шрифты (pygame.font должен быть инициализирован через pygame.init())
        self.font_big = pygame.font.SysFont(None, 72)
        self.font_mid = pygame.font.SysFont(None, 42)
        self.font_small = pygame.font.SysFont(None, 28)

        # Позиции/размеры для стимула
        self.center = (self.w // 2, self.h // 2)
        self.shape_size = min(self.w, self.h) // 6  # размер фигуры

        # Цвета UI
        self.bg_color = (15, 15, 20)
        self.ui_color = (230, 230, 230)

        # Перевод названий цветов в RGB
        self.color_map = {
            "red": (220, 60, 60),
            "green": (60, 200, 120),
            "blue": (70, 120, 240),
            "yellow": (240, 210, 60),
        }

    # -----------------------
    # Базовые методы экрана
    # -----------------------

    def clear(self) -> None:
        """Очистить экран (залить фоном)."""
        self.screen.fill(self.bg_color)

    def present(self) -> None:
        """Показать кадр."""
        pygame.display.flip()

    # -----------------------
    # Рисование элементов
    # -----------------------

    def draw_cue(self, task_id: str, time_left_ms: Optional[int] = None) -> None:
        """
        Рисует cue: какая сейчас задача (COLOR/SHAPE).
        time_left_ms — опционально, если захочешь показывать таймер.
        """
        text = task_id  # task_id у нас строка: "COLOR" или "SHAPE"
        surf = self.font_big.render(text, True, self.ui_color)
        rect = surf.get_rect(center=(self.center[0], self.h * 0.22))
        self.screen.blit(surf, rect)

        # Если хотим — показываем маленький таймер
        if time_left_ms is not None:
            t_surf = self.font_small.render(f"{time_left_ms} ms", True, self.ui_color)
            t_rect = t_surf.get_rect(center=(self.center[0], self.h * 0.22 + 55))
            self.screen.blit(t_surf, t_rect)

    def draw_stimulus(self, stimulus) -> None:
        """
        Рисует стимул:
        - stimulus.color: "red"/"green"/...
        - stimulus.shape: "circle"/"triangle"/"square"/"cross"
        """
        color = self.color_map.get(getattr(stimulus, "color", ""), (200, 200, 200))
        shape = getattr(stimulus, "shape", "circle")

        if shape == "circle":
            self._draw_circle(color)
        elif shape == "square":
            self._draw_square(color)
        elif shape == "triangle":
            self._draw_triangle(color)
        elif shape == "cross":
            self._draw_cross(color)
        else:
            # Если форма неизвестна — рисуем круг по умолчанию
            self._draw_circle(color)

    def draw_feedback(self, is_correct: Optional[bool], message: Optional[str] = None) -> None:
        """
        Рисует фидбек.
        is_correct:
          - True  -> Correct
          - False -> Incorrect
          - None  -> ничего не рисуем (или message)
        message — можно явно передать "Too slow", "Miss", и т.п.
        """
        if message is None:
            if is_correct is True:
                message = "Correct"
            elif is_correct is False:
                message = "Incorrect"
            else:
                return

        surf = self.font_mid.render(message, True, self.ui_color)
        rect = surf.get_rect(center=(self.center[0], self.h * 0.78))
        self.screen.blit(surf, rect)

    def draw_hud(self, block_progress: Tuple[int, int], score: int = 0) -> None:
        """
        HUD: прогресс и очки.
        block_progress = (current_trial_index+1, total_trials)
        """
        cur, total = block_progress
        left_text = f"Trial: {cur}/{total}"
        right_text = f"Score: {score}"

        left = self.font_small.render(left_text, True, self.ui_color)
        right = self.font_small.render(right_text, True, self.ui_color)

        self.screen.blit(left, (20, 15))
        self.screen.blit(right, (self.w - right.get_width() - 20, 15))

    # -----------------------
    # Внутренние функции рисования фигур
    # -----------------------

    def _draw_circle(self, color) -> None:
        pygame.draw.circle(self.screen, color, self.center, self.shape_size)

    def _draw_square(self, color) -> None:
        rect = pygame.Rect(0, 0, self.shape_size * 2, self.shape_size * 2)
        rect.center = self.center
        pygame.draw.rect(self.screen, color, rect)

    def _draw_triangle(self, color) -> None:
        cx, cy = self.center
        s = self.shape_size * 2
        points = [
            (cx, cy - s // 2),
            (cx - s // 2, cy + s // 2),
            (cx + s // 2, cy + s // 2),
        ]
        pygame.draw.polygon(self.screen, color, points)

    def _draw_cross(self, color) -> None:
        # рисуем крест как две толстые линии
        cx, cy = self.center
        s = self.shape_size * 2
        thickness = max(6, self.shape_size // 3)

        pygame.draw.line(self.screen, color, (cx - s // 2, cy - s // 2), (cx + s // 2, cy + s // 2), thickness)
        pygame.draw.line(self.screen, color, (cx - s // 2, cy + s // 2), (cx + s // 2, cy - s // 2), thickness)
