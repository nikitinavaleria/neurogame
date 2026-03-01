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
        self.ui_scale = max(0.75, min(1.15, min(self.w / 1600.0, self.h / 900.0)))
        self.compact = self.w < 1280 or self.h < 760
        self.font_big = self._make_font(max(30, int(40 * self.ui_scale)), bold=True)
        self.font_huge = self._make_font(max(48, int(72 * self.ui_scale)), bold=True)
        self.font_mid = self._make_font(max(22, int(28 * self.ui_scale)))
        self.font_small = self._make_font(max(16, int(21 * self.ui_scale)))
        self.font_tiny = self._make_font(max(14, int(17 * self.ui_scale)))
        self.stars = self._build_stars(80)

        margin = max(8, min(20, self.w // 70))
        top = max(60, min(84, self.h // 12))
        gap = max(8, min(18, self.w // 90))
        main_h = max(260, self.h - top - margin)
        available_w = max(320, self.w - (margin * 2) - (gap * 2))

        if self.compact:
            left_w = max(135, min(220, int(available_w * 0.24)))
            right_w = max(170, min(260, int(available_w * 0.27)))
        else:
            left_w = max(150, min(250, int(available_w * 0.22)))
            right_w = max(220, min(330, int(available_w * 0.28)))
        center_w = available_w - left_w - right_w
        if center_w < 280:
            shortage = 280 - center_w
            shrink_left = min(max(0, left_w - 120), shortage // 2)
            left_w -= shrink_left
            shortage -= shrink_left
            shrink_right = min(max(0, right_w - 180), shortage)
            right_w -= shrink_right
            center_w = available_w - left_w - right_w

        self.left_panel = pygame.Rect(margin, top, left_w, main_h)
        self.center_panel = pygame.Rect(self.left_panel.right + gap, top, center_w, main_h)
        self.right_panel = pygame.Rect(self.center_panel.right + gap, top, right_w, main_h)

        left_gap = 10 if self.compact else 12
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

        panel_pad = 8 if self.compact else 10
        task_gap = 8 if self.compact else 10
        self.task_panel_height = (self.right_panel.height - panel_pad * 2 - task_gap * 2) // 3
        self.task_panels = [
            pygame.Rect(
                self.right_panel.x + panel_pad,
                self.right_panel.y + panel_pad + i * (self.task_panel_height + task_gap),
                self.right_panel.width - panel_pad * 2,
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
        planets_visited: int,
    ) -> None:
        x = self.left_stats_panel.x + 16
        y = self.left_stats_panel.y + 14
        header = self.font_mid.render("Статистика", True, self.theme.accent)
        self.screen.blit(header, (x, y))
        lines = [
            f"Планет: {planets_visited}",
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

    def draw_mission_panel(
        self,
        flight_progress: float,
        zone_quality: float,
        tasks_done: int,
        total_tasks: int,
        planets_visited: int,
    ) -> None:
        rect = self.center_panel
        x = rect.x + 16
        y = rect.y + 12
        header = self.font_mid.render("Маршрут миссии", True, self.theme.accent)
        self.screen.blit(header, (x, y))

        sub = self.font_tiny.render("Удерживай точность и темп, чтобы долететь", True, self.theme.text)
        self.screen.blit(sub, (x, y + 30))

        track_top = y + 72
        track_bottom = rect.bottom - 42
        track_x = rect.x + rect.width // 2
        pygame.draw.line(self.screen, self.theme.border, (track_x, track_top), (track_x, track_bottom), 4)

        quality_color = (
            int(80 + 120 * zone_quality),
            int(110 + 100 * zone_quality),
            int(120 + 90 * zone_quality),
        )
        glow_radius = 22 + int(10 * zone_quality)
        pygame.draw.circle(self.screen, quality_color, (track_x, track_top), glow_radius, width=2)

        progress = max(0.0, min(1.0, flight_progress))
        rocket_y = int(track_bottom - (track_bottom - track_top) * progress)
        rocket = [
            (track_x, rocket_y - 20),
            (track_x - 12, rocket_y + 14),
            (track_x + 12, rocket_y + 14),
        ]
        pygame.draw.polygon(self.screen, self.theme.accent, rocket)
        pygame.draw.rect(self.screen, (220, 90, 40), (track_x - 5, rocket_y + 14, 10, 10))

        goal_label = self.font_tiny.render("ЦЕЛЬ", True, self.theme.text)
        self.screen.blit(goal_label, (track_x + 24, track_top - 10))

        progress_line = self.font_small.render(
            f"Прогресс: {tasks_done}/{total_tasks}",
            True,
            self.theme.text,
        )
        self.screen.blit(progress_line, (x, rect.bottom - 28))
        planets_line = self.font_small.render(
            f"Посещено планет: {planets_visited}",
            True,
            self.theme.text,
        )
        self.screen.blit(planets_line, (x, rect.bottom - 54))

    def draw_task_panel(self, rect: pygame.Rect, title: str, active: bool) -> None:
        pygame.draw.rect(self.screen, self.theme.panel, rect, border_radius=10)
        pygame.draw.rect(self.screen, self.theme.border, rect, width=2, border_radius=10)
        color = self.theme.accent if active else self.theme.text
        self._draw_fitted_text(
            text=title,
            rect=pygame.Rect(rect.x + 10, rect.y + 6, rect.width - 20, self.font_small.get_height() + 6),
            color=color,
            align="left",
        )

    def draw_button(self, rect: pygame.Rect, label: str, active: bool = False) -> None:
        fill = (26, 34, 52) if not active else (22, 52, 66)
        border = self.theme.accent if active else self.theme.border
        pygame.draw.rect(self.screen, fill, rect, border_radius=10)
        pygame.draw.rect(self.screen, border, rect, width=2, border_radius=10)
        self._draw_fitted_text(text=label, rect=rect, color=self.theme.text, align="center")

    def _draw_fitted_text(
        self,
        text: str,
        rect: pygame.Rect,
        color: Tuple[int, int, int],
        align: str = "center",
    ) -> None:
        fonts = [self.font_small, self.font_tiny]
        surf = None
        for font in fonts:
            if font.size(text)[0] <= rect.width - 12:
                surf = font.render(text, True, color)
                break
        if surf is None:
            fallback_size = max(12, int(self.font_tiny.get_height() * 0.85))
            fallback = self._make_font(fallback_size)
            clipped = text
            while len(clipped) > 3 and fallback.size(clipped + "...")[0] > rect.width - 12:
                clipped = clipped[:-1]
            surf = fallback.render((clipped + "...") if clipped != text else text, True, color)
        if align == "left":
            text_rect = surf.get_rect(midleft=(rect.x + 6, rect.centery))
        else:
            text_rect = surf.get_rect(center=rect.center)
        self.screen.blit(surf, text_rect)

    def _make_font(self, size: int, bold: bool = False) -> pygame.font.Font:
        candidates = [
            "sfprotext",
            "sfprodisplay",
            "helveticaneue",
            "avenirnext",
            "avenir",
            "segoeui",
            "arial",
        ]
        for name in candidates:
            path = pygame.font.match_font(name)
            if path:
                font = pygame.font.Font(path, size)
                if bold:
                    font.set_bold(True)
                return font
        return pygame.font.SysFont(None, size, bold=bold)

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
