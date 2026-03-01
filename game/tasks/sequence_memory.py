import random
from typing import List

import pygame

from game.runtime.models import TaskSpec
from game.tasks.base import TaskBase, TaskRenderContext
from game.tasks.input_utils import read_left_right_key


class SequenceMemoryTask(TaskBase):
    task_id = "sequence_memory"

    def __init__(self, spec: TaskSpec, rng: random.Random) -> None:
        super().__init__(spec)
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        self.sequence: List[str] = [rng.choice(alphabet) for _ in range(spec.difficulty["seq_len"])]
        self.query_symbol = rng.choice(alphabet)
        self.answer_is_yes = self.query_symbol in self.sequence
        max_show = int(spec.difficulty["time_limit_ms"] * 0.8)
        base_show = 900 + 200 * len(self.sequence)
        self.show_until_ms = self.created_ms + min(base_show, max_show)
        self.query_ready_ms = self.show_until_ms + spec.difficulty["retention_delay_ms"]
        latest_query = self.deadline_ms - 200
        if self.query_ready_ms > latest_query:
            self.query_ready_ms = latest_query

    def handle_event(self, event: pygame.event.Event, now_ms: int) -> None:
        if self.finished_ms is not None:
            return
        if now_ms < self.query_ready_ms:
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
        now_ms = pygame.time.get_ticks()
        if now_ms < self.show_until_ms:
            seq = " ".join(self.sequence)
            surf = ctx.font_big.render(seq, True, ctx.color_main)
            screen.blit(surf, (x, y + min(64, max_h // 3)))
            hint_text = "Запомни последовательность"
            if ctx.font_small.size(hint_text)[0] > ctx.rect.width - 32:
                hint_text = "Запомни символы"
            hint = ctx.font_small.render(hint_text, True, ctx.color_main)
            screen.blit(hint, (x, y + max_h - 22))
            return

        if now_ms < self.query_ready_ms:
            return

        question = f"Был ли '{self.query_symbol}'?"
        surf = ctx.font_mid.render(question, True, ctx.color_main)
        screen.blit(surf, (x, y + min(64, max_h // 3)))
        hint = ctx.font_small.render("F - да, J - нет", True, ctx.color_main)
        screen.blit(hint, (x, y + max_h - 22))
