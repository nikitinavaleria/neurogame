from dataclasses import dataclass
from typing import List, Optional, Tuple

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
        self.font_mid = pygame.font.SysFont(None, 26)
        self.font_small = pygame.font.SysFont(None, 21)
        self.font_tiny = pygame.font.SysFont(None, 18)
        self.stars = self._build_stars(80)

        self.left_panel = pygame.Rect(20, 20, 320, self.h - 140)
        self.center_panel = pygame.Rect(360, 20, 520, 220)
        self.right_panel = pygame.Rect(900, 20, 360, self.h - 140)
        self.footer_panel = pygame.Rect(20, self.h - 100, self.w - 40, 80)

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
        for rect in [self.left_panel, self.center_panel, self.right_panel, self.footer_panel]:
            pygame.draw.rect(self.screen, self.theme.panel, rect, border_radius=10)
            pygame.draw.rect(self.screen, self.theme.border, rect, width=2, border_radius=10)
        pygame.draw.line(
            self.screen,
            self.theme.border,
            (self.center_panel.x, self.center_panel.y + 70),
            (self.center_panel.x + self.center_panel.width, self.center_panel.y + 70),
            1,
        )

    def draw_title(self, text: str) -> None:
        surf = self.font_mid.render(text, True, self.theme.text)
        rect = surf.get_rect(center=(self.w // 2, 12))
        self.screen.blit(surf, rect)

    def draw_status(
        self,
        stability: float,
        load: int,
        tasks_done: int,
        total_tasks: int,
        level: int,
    ) -> None:
        line1 = f"Стабильность: {int(stability * 100)}%   Нагрузка: {load}"
        line2 = f"Задачи: {tasks_done}/{total_tasks}   Уровень: {level}"
        surf1 = self.font_mid.render(line1, True, self.theme.text)
        surf2 = self.font_small.render(line2, True, self.theme.text)
        self.screen.blit(surf1, (self.center_panel.x + 20, self.center_panel.y + 18))
        self.screen.blit(surf2, (self.center_panel.x + 20, self.center_panel.y + 46))

    def draw_task_list(self, tasks: List[Tuple[str, int]], focused_index: Optional[int]) -> None:
        x = self.left_panel.x + 20
        y = self.left_panel.y + 54
        header = self.font_mid.render("Активные потоки", True, self.theme.accent)
        self.screen.blit(header, (x, self.left_panel.y + 18))

        for i, (name, time_left_ms) in enumerate(tasks):
            color = self.theme.alert if time_left_ms < 400 else self.theme.text
            label = f"{i + 1}. {name}  {time_left_ms} ms"
            if focused_index == i:
                label = f"> {label}"
            surf = self.font_small.render(label, True, color)
            self.screen.blit(surf, (x, y))
            y += 26

    def draw_footer(self, hint: str) -> None:
        surf = self.font_small.render(hint, True, self.theme.text)
        self.screen.blit(surf, (self.footer_panel.x + 20, self.footer_panel.y + 25))

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
