import random
from typing import Dict, Tuple

import pygame

from data.models import TaskSpec
from game.tasks.base import TaskBase, TaskRenderContext
from game.tasks.input_utils import read_left_right_key


COLORS = {
    "red": (220, 60, 60),
    "blue": (70, 120, 240),
}

SHAPES = ["circle", "square"]

ACTION_MAP: Dict[str, Dict[str, str]] = {
    "COLOR": {"red": "F", "blue": "J"},
    "SHAPE": {"circle": "F", "square": "J"},
}


class RuleSwitchTask(TaskBase):
    task_id = "rule_switch"

    def __init__(self, spec: TaskSpec, rng: random.Random) -> None:
        super().__init__(spec)
        self.rule = spec.payload["rule"]
        self.color = rng.choice(list(COLORS.keys()))
        self.shape = rng.choice(SHAPES)
        if self.rule == "COLOR":
            self.correct_action = ACTION_MAP["COLOR"][self.color]
        else:
            self.correct_action = ACTION_MAP["SHAPE"][self.shape]

    def handle_event(self, event: pygame.event.Event, now_ms: int) -> None:
        if self.finished_ms is not None:
            return
        key = read_left_right_key(event)
        if key is None:
            return
        self.response = "F" if key == "LEFT" else "J"
        self.correct = self.response == self.correct_action
        self.finished_ms = now_ms

    def render(self, screen: pygame.Surface, ctx: TaskRenderContext) -> None:
        x = ctx.rect.x + 16
        y = ctx.rect.y + 30
        max_h = ctx.rect.height - 44
        center_x = ctx.rect.x + ctx.rect.width // 2
        rule_label = "ЦВЕТ" if self.rule == "COLOR" else "ФОРМА"
        cue = ctx.font_small.render(f"Правило: {rule_label}", True, ctx.color_main)
        screen.blit(cue, (x, y + 28))

        if self.rule == "COLOR":
            map_hint = "F - красный, J - синий"
        else:
            map_hint = "F - круг, J - квадрат"
        hint_map = ctx.font_small.render(map_hint, True, ctx.color_main)
        screen.blit(hint_map, (x, y + min(56, max_h // 3)))

        color = COLORS[self.color]
        top_limit = y + min(56, max_h // 3) + 26
        bottom_limit = y + max_h - 36
        shape_area_h = max(44, bottom_limit - top_limit)
        cy = top_limit + shape_area_h // 2
        size = min(ctx.rect.width // 6, shape_area_h // 2 - 4)
        size = max(18, size)
        if self.shape == "circle":
            pygame.draw.circle(screen, color, (center_x, cy), size)
        else:
            rect = pygame.Rect(0, 0, size * 2, size * 2)
            rect.center = (center_x, cy)
            pygame.draw.rect(screen, color, rect)

        hint = ctx.font_small.render("Нажми по текущему правилу", True, ctx.color_main)
        screen.blit(hint, (x, y + max_h - 22))
