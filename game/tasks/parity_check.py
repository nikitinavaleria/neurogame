import random

import pygame

from game.runtime.models import TaskSpec
from game.tasks.base import TaskBase, TaskRenderContext, render_fitted_text, wrap_text
from game.tasks.input_utils import read_left_right_key


def _is_prime(value: int) -> bool:
    n = abs(value)
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    limit = int(n**0.5)
    for div in range(3, limit + 1, 2):
        if n % div == 0:
            return False
    return True


class ParityCheckTask(TaskBase):
    task_id = "parity_check"

    def __init__(self, spec: TaskSpec, rng: random.Random) -> None:
        super().__init__(spec)
        low = spec.difficulty["min_value"]
        high = spec.difficulty["max_value"]
        complexity = int(spec.difficulty.get("question_complexity", 1))
        self.value = rng.randint(low, high)

        predicates = []

        predicates.append(("Число четное?", lambda v: (v % 2) == 0, "even"))

        if complexity >= 2:
            threshold = rng.randint(low, high)
            predicates.append((f"Число больше {threshold}?", lambda v, t=threshold: v > t, "greater_than"))

        if complexity >= 3:
            div = rng.choice([3, 5])
            predicates.append((f"Число кратно {div}?", lambda v, d=div: (v % d) == 0, "divisible"))

        if complexity >= 4:
            predicates.append(("Число простое?", _is_prime, "prime"))

        if complexity >= 5:
            digit = rng.randint(0, 9)
            predicates.append(
                (
                    f"Содержит цифру {digit}?",
                    lambda v, d=digit: str(d) in str(abs(v)),
                    "contains_digit",
                )
            )

        if complexity >= 6:
            predicates.append(
                (
                    "Сумма цифр четная?",
                    lambda v: (sum(int(ch) for ch in str(abs(v))) % 2) == 0,
                    "digit_sum_even",
                )
            )

        if complexity >= 7:
            endings = rng.choice([(1, 3, 7, 9), (0, 2, 4, 6, 8), (0, 5)])
            ending_text = ", ".join(str(e) for e in endings)
            predicates.append(
                (
                    f"Оканчивается на {ending_text}?",
                    lambda v, allowed=endings: abs(v) % 10 in allowed,
                    "ending_in",
                )
            )

        question, fn, question_type = rng.choice(predicates)
        self.question_text = question
        self.answer_is_yes = fn(self.value)
        self.spec.payload["question_type"] = question_type
        self.spec.payload["question_text"] = self.question_text

    def handle_event(self, event: pygame.event.Event, now_ms: int) -> None:
        if self.finished_ms is not None:
            return
        key = read_left_right_key(event)
        if key is None:
            return
        self.response = "yes" if key == "LEFT" else "no"
        self.correct = (self.response == "yes") == self.answer_is_yes
        self.finished_ms = now_ms

    def render(self, screen: pygame.Surface, ctx: TaskRenderContext) -> None:
        x = ctx.rect.x + 16
        y = ctx.rect.y + 30
        max_h = ctx.rect.height - 44
        max_text_width = ctx.rect.width - 32
        title_lines = wrap_text(self.question_text, ctx.font_small, max_text_width)
        value = render_fitted_text(
            str(self.value),
            ctx.color_accent,
            [ctx.font_big, ctx.font_mid, ctx.font_small],
            max_text_width,
        )
        hint = ctx.font_small.render("F - да, J - нет", True, ctx.color_main)

        title_y = y + min(24, max_h // 5)
        line_gap = ctx.font_small.get_height() + 4
        for idx, line in enumerate(title_lines[:3]):
            title = ctx.font_small.render(line, True, ctx.color_main)
            screen.blit(title, (x, title_y + idx * line_gap))

        value_y = title_y + min(72, max_h // 2)
        if title_lines:
            value_y = max(value_y, title_y + len(title_lines[:3]) * line_gap + 14)
        screen.blit(value, (x, value_y))
        screen.blit(hint, (x, y + max_h - 22))
