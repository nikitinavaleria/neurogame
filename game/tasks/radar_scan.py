import random

import pygame

from data.models import TaskSpec
from game.tasks.base import TaskBase, TaskRenderContext
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

        title = ctx.font_mid.render("Есть метка угрозы?", True, ctx.color_main)
        sub = ctx.font_small.render(f"Ищи символ: {self.target_symbol}", True, ctx.color_main)
        value = ctx.font_big.render(self.signal, True, ctx.color_accent)
        hint = ctx.font_small.render("F - да, J - нет", True, ctx.color_main)

        # Layout is purely flow-based to avoid overlap after font/style changes.
        cursor_y = y + 24
        screen.blit(title, (x, cursor_y))
        cursor_y += title.get_height() + 10

        screen.blit(sub, (x, cursor_y))
        cursor_y += sub.get_height() + 14

        value_y = min(cursor_y, bottom_y - hint.get_height() - value.get_height() - 10)
        screen.blit(value, (x, value_y))

        hint_y = max(value_y + value.get_height() + 8, bottom_y - hint.get_height())
        screen.blit(hint, (x, hint_y))
