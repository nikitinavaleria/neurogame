import random

import pygame

from game.runtime.models import TaskSpec
from game.tasks.base import TaskBase, TaskRenderContext, render_fitted_text, wrap_text
from game.tasks.input_utils import read_left_right_key


TARGET_SYMBOLS = ["X", "K", "R", "N", "Z", "M", "V"]
BASE_ALPHABET = ["A", "C", "D", "E", "G", "H", "J", "L", "P", "Q", "S", "T", "U", "W", "Y"]


class RadarScanTask(TaskBase):
    task_id = "radar_scan"

    def __init__(self, spec: TaskSpec, rng: random.Random) -> None:
        super().__init__(spec)
        signal_len = spec.difficulty["signal_len"]
        threat_rate = spec.difficulty["threat_rate"]
        target_pool_size = int(spec.difficulty.get("target_pool_size", 1))
        pool_size = max(1, min(len(TARGET_SYMBOLS), target_pool_size))
        self.target_symbol = rng.choice(TARGET_SYMBOLS[:pool_size])

        alphabet = [ch for ch in BASE_ALPHABET if ch != self.target_symbol]
        self.signal = "".join(rng.choice(alphabet) for _ in range(signal_len))
        self.has_threat = rng.random() < threat_rate
        if self.has_threat:
            idx = rng.randrange(signal_len)
            self.signal = self.signal[:idx] + self.target_symbol + self.signal[idx + 1 :]

        self.spec.payload["target_symbol"] = self.target_symbol

    def handle_event(self, event: pygame.event.Event, now_ms: int) -> None:
        if self.finished_ms is not None:
            return
        key = read_left_right_key(event)
        if key is None:
            return
        self.response = "yes" if key == "LEFT" else "no"
        self.correct = (self.response == "yes") == self.has_threat
        self.finished_ms = now_ms

    def render(self, screen: pygame.Surface, ctx: TaskRenderContext) -> None:
        x = ctx.rect.x + 16
        y = ctx.rect.y + 30
        bottom_y = ctx.rect.bottom - 24
        max_text_width = ctx.rect.width - 32
        title_lines = wrap_text("Есть метка угрозы?", ctx.font_small, max_text_width)
        sub_lines = wrap_text(f"Ищи символ: {self.target_symbol}", ctx.font_small, max_text_width)
        value = render_fitted_text(
            self.signal,
            ctx.color_accent,
            [ctx.font_big, ctx.font_mid, ctx.font_small],
            max_text_width,
        )
        hint = ctx.font_small.render("F - да, J - нет", True, ctx.color_main)

        cursor_y = y + 24
        line_gap = ctx.font_small.get_height() + 4
        for line in title_lines[:2]:
            title = ctx.font_small.render(line, True, ctx.color_main)
            screen.blit(title, (x, cursor_y))
            cursor_y += line_gap
        cursor_y += 6

        for line in sub_lines[:2]:
            sub = ctx.font_small.render(line, True, ctx.color_main)
            screen.blit(sub, (x, cursor_y))
            cursor_y += line_gap
        cursor_y += 10

        max_value_y = bottom_y - hint.get_height() - value.get_height() - 10
        min_value_y = y + 24
        if max_value_y >= cursor_y:
            value_y = cursor_y
        else:
            value_y = max(min_value_y, max_value_y)
        screen.blit(value, (x, value_y))

        hint_y = min(bottom_y - hint.get_height(), value_y + value.get_height() + 8)
        hint_y = max(hint_y, value_y + value.get_height() + 4)
        screen.blit(hint, (x, hint_y))
