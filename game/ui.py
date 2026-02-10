from dataclasses import dataclass
import math
from typing import Optional, Tuple

import pygame


@dataclass(frozen=True)
class UiTheme:
    bg: Tuple[int, int, int] = (8, 10, 20)
    panel: Tuple[int, int, int] = (18, 22, 36)
    border: Tuple[int, int, int] = (40, 60, 90)
    text: Tuple[int, int, int] = (220, 230, 245)
    accent: Tuple[int, int, int] = (0, 210, 210)
    alert: Tuple[int, int, int] = (240, 120, 40)


class GameUI:
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.w, self.h = screen.get_size()
        self.theme = UiTheme()
        self.font_big = pygame.font.SysFont(None, 40)
        self.font_huge = pygame.font.SysFont(None, 72)
        self.font_mid = pygame.font.SysFont(None, 26)
        self.font_small = pygame.font.SysFont(None, 21)
        self.font_tiny = pygame.font.SysFont(None, 18)
        self.stars = self._build_stars(80)

        margin = 20
        top = 84
        gap = 20
        main_h = self.h - top - margin
        left_w = 250
        right_w = 330
        center_w = self.w - (margin * 2) - (gap * 2) - left_w - right_w

        self.left_panel = pygame.Rect(margin, top, left_w, main_h)
        self.center_panel = pygame.Rect(self.left_panel.right + gap, top, center_w, main_h)
        self.right_panel = pygame.Rect(self.center_panel.right + gap, top, right_w, main_h)

        left_gap = 12
        usable_h = self.left_panel.height - left_gap * 2
        focus_h = int(usable_h * 0.33)
        help_h = int(usable_h * 0.20)
        stats_h = usable_h - focus_h - help_h
        self.left_focus_panel = pygame.Rect(
            self.left_panel.x,
            self.left_panel.y,
            self.left_panel.width,
            focus_h,
        )
        self.left_stats_panel = pygame.Rect(
            self.left_panel.x,
            self.left_focus_panel.bottom + left_gap,
            self.left_panel.width,
            stats_h,
        )
        self.left_help_panel = pygame.Rect(
            self.left_panel.x,
            self.left_stats_panel.bottom + left_gap,
            self.left_panel.width,
            help_h,
        )

        self.task_panel_height = (self.right_panel.height - 20 * 2) // 3
        self.task_panels = [
            pygame.Rect(
                self.right_panel.x + 10,
                self.right_panel.y + 10 + i * (self.task_panel_height + 10),
                self.right_panel.width - 20,
                self.task_panel_height,
            )
            for i in range(3)
        ]

    def clear(self) -> None:
        self.screen.fill(self.theme.bg)
        for (x, y, r) in self.stars:
            pygame.draw.circle(self.screen, (20, 30, 55), (x, y), r)

    def draw_frame(self) -> None:
        for rect in [
            self.left_panel,
            self.center_panel,
            self.right_panel,
            self.left_focus_panel,
            self.left_stats_panel,
            self.left_help_panel,
        ]:
            pygame.draw.rect(self.screen, self.theme.panel, rect, border_radius=10)
            pygame.draw.rect(self.screen, self.theme.border, rect, width=2, border_radius=10)

    def draw_title(self, text: str) -> None:
        shadow = self.font_big.render(text, True, (12, 20, 40))
        main = self.font_big.render(text, True, self.theme.accent)
        rect = main.get_rect(center=(self.w // 2, 48))
        self.screen.blit(shadow, (rect.x + 2, rect.y + 2))
        self.screen.blit(main, rect)

    def draw_status(
        self,
        stability: float,
        tasks_done: int,
        total_tasks: int,
        level: int,
    ) -> None:
        x = self.left_stats_panel.x + 16
        y = self.left_stats_panel.y + 14
        header = self.font_mid.render("Статистика", True, self.theme.accent)
        self.screen.blit(header, (x, y))
        lines = [
            f"Уровень: {level}",
            f"Стабильность: {int(stability * 100)}%",
            f"Задачи: {tasks_done}/{total_tasks}",
        ]
        yy = y + 38
        for line in lines:
            surf = self.font_small.render(line, True, self.theme.text)
            self.screen.blit(surf, (x, yy))
            yy += 28

    def draw_focus_panel(
        self, task_name: Optional[str], time_left_ms: Optional[int], show_timeout_alert: bool
    ) -> None:
        x = self.left_focus_panel.x + 16
        y = self.left_focus_panel.y + 12
        header = self.font_mid.render("Текущая задача", True, self.theme.accent)
        self.screen.blit(header, (x, y))

        if show_timeout_alert:
            late = self.font_mid.render("Слишком поздно", True, self.theme.alert)
            self.screen.blit(late, (x, y + 98))
            return

        if task_name is None or time_left_ms is None:
            return

        task = self.font_small.render(task_name, True, self.theme.text)
        self.screen.blit(task, (x, y + 40))

        seconds_left = max(0, math.ceil(time_left_ms / 1000.0))
        sec_text = self.font_huge.render(str(seconds_left), True, self.theme.accent)
        self.screen.blit(sec_text, (x, y + 64))
        unit_text = self.font_small.render("сек до конца", True, self.theme.text)
        self.screen.blit(unit_text, (x, y + 136))

    def draw_help_panel(self) -> None:
        x = self.left_help_panel.x + 16
        y = self.left_help_panel.y + 12
        header = self.font_mid.render("Шпаргалка", True, self.theme.accent)
        self.screen.blit(header, (x, y))
        lines = [
            "F/J действие",
            "esc выход",
        ]
        yy = y + 38
        for line in lines:
            surf = self.font_small.render(line, True, self.theme.text)
            self.screen.blit(surf, (x, yy))
            yy += 28

    def draw_task_panel(self, rect: pygame.Rect, title: str, active: bool) -> None:
        pygame.draw.rect(self.screen, self.theme.panel, rect, border_radius=10)
        pygame.draw.rect(self.screen, self.theme.border, rect, width=2, border_radius=10)
        color = self.theme.accent if active else self.theme.text
        label = self.font_small.render(title, True, color)
        self.screen.blit(label, (rect.x + 14, rect.y + 10))

    def _build_stars(self, count: int):
        rng = (self.w * 73856093) ^ (self.h * 19349663)
        stars = []
        x = rng & 0xFFFF
        y = (rng >> 4) & 0xFFFF
        for _ in range(count):
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF
            y = (y * 1103515245 + 54321) & 0x7FFFFFFF
            stars.append((x % self.w, y % self.h, (x % 2) + 1))
        return stars
