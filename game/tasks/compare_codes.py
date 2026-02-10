import random
from typing import Tuple

import pygame

from data.models import TaskSpec
from game.tasks.base import TaskBase, TaskRenderContext
from game.tasks.input_utils import read_left_right_key


def _build_code(rng: random.Random, length: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(rng.choice(alphabet) for _ in range(length))


def _make_pair(rng: random.Random, length: int, similarity_rate: float) -> Tuple[str, str, bool]:
    code_a = _build_code(rng, length)
    if rng.random() < similarity_rate:
        index = rng.randrange(length)
        char_options = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".replace(code_a[index], "")
        code_b = code_a[:index] + rng.choice(char_options) + code_a[index + 1 :]
        return code_a, code_b, False
    return code_a, code_a, True


class CompareCodesTask(TaskBase):
    task_id = "compare_codes"

    def __init__(self, spec: TaskSpec, rng: random.Random) -> None:
        super().__init__(spec)
        length = spec.difficulty["code_len"]
        similarity = spec.difficulty["similarity_rate"]
        self.code_a, self.code_b, self.is_match = _make_pair(rng, length, similarity)

    def handle_event(self, event: pygame.event.Event, now_ms: int) -> None:
        if self.finished_ms is not None:
            return
        key = read_left_right_key(event)
        if key is None:
            return
        self.response = "match" if key == "LEFT" else "mismatch"
        self.correct = (self.response == "match") == self.is_match
        self.finished_ms = now_ms

    def render(self, screen: pygame.Surface, ctx: TaskRenderContext) -> None:
        x = ctx.rect.x + 16
        y = ctx.rect.y + 30
        max_h = ctx.rect.height - 44
        code_a = ctx.font_big.render(self.code_a, True, ctx.color_main)
        code_b = ctx.font_big.render(self.code_b, True, ctx.color_main)
        spacing = min(54, max(30, max_h // 5))
        screen.blit(code_a, (x, y + spacing))
        screen.blit(code_b, (x, y + spacing * 2))

        hint = ctx.font_small.render("F - да, J - нет", True, ctx.color_main)
        screen.blit(hint, (x, y + max_h - 22))
