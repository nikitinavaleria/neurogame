import random
import math
from typing import List, Tuple

import pygame

from data.models import TaskSpec
from game.tasks.base import TaskBase, TaskRenderContext
from game.tasks.input_utils import read_left_right_key


COLORS: List[Tuple[str, Tuple[int, int, int], str]] = [
    ("red", (220, 60, 60), "красный"),
    ("blue", (70, 120, 240), "синий"),
    ("green", (80, 180, 100), "зелёный"),
    ("yellow", (230, 200, 70), "жёлтый"),
    ("orange", (235, 140, 50), "оранжевый"),
    ("purple", (150, 90, 220), "фиолетовый"),
    ("cyan", (70, 190, 210), "бирюзовый"),
]

SHAPES: List[Tuple[str, str]] = [
    ("circle", "круг"),
    ("square", "квадрат"),
    ("triangle", "треугольник"),
    ("diamond", "ромб"),
    ("pentagon", "пятиугольник"),
    ("hexagon", "шестиугольник"),
    ("star", "звезда"),
]


def _polygon_points(cx: int, cy: int, radius: int, count: int, angle_shift: float = 0.0):
    points = []
    for i in range(count):
        angle = angle_shift + (2 * 3.14159265 * i / count)
        x = int(cx + radius * math.cos(angle))
        y = int(cy + radius * math.sin(angle))
        points.append((x, y))
    return points


def _draw_shape(screen: pygame.Surface, shape: str, color: Tuple[int, int, int], center_x: int, center_y: int, size: int):
    if shape == "circle":
        pygame.draw.circle(screen, color, (center_x, center_y), size)
        return
    if shape == "square":
        rect = pygame.Rect(0, 0, size * 2, size * 2)
        rect.center = (center_x, center_y)
        pygame.draw.rect(screen, color, rect)
        return
    if shape == "triangle":
        points = [
            (center_x, center_y - size),
            (center_x - size, center_y + size),
            (center_x + size, center_y + size),
        ]
        pygame.draw.polygon(screen, color, points)
        return
    if shape == "diamond":
        points = [
            (center_x, center_y - size),
            (center_x - size, center_y),
            (center_x, center_y + size),
            (center_x + size, center_y),
        ]
        pygame.draw.polygon(screen, color, points)
        return
    if shape == "pentagon":
        pygame.draw.polygon(screen, color, _polygon_points(center_x, center_y, size, 5, -3.14159265 / 2))
        return
    if shape == "hexagon":
        pygame.draw.polygon(screen, color, _polygon_points(center_x, center_y, size, 6, 0.0))
        return
    if shape == "star":
        outer = _polygon_points(center_x, center_y, size, 5, -3.14159265 / 2)
        inner = _polygon_points(center_x, center_y, max(8, size // 2), 5, -3.14159265 / 2 + 3.14159265 / 5)
        points = []
        for i in range(5):
            points.append(outer[i])
            points.append(inner[i])
        pygame.draw.polygon(screen, color, points)
        return

    pygame.draw.circle(screen, color, (center_x, center_y), size)


class RuleSwitchTask(TaskBase):
    task_id = "rule_switch"

    def __init__(self, spec: TaskSpec, rng: random.Random) -> None:
        super().__init__(spec)
        self.rule = spec.payload["rule"]
        complexity = int(spec.difficulty.get("rule_complexity", 2))

        colors_count = max(2, min(len(COLORS), complexity))
        shapes_count = max(2, min(len(SHAPES), complexity))

        active_colors = COLORS[:colors_count]
        active_shapes = SHAPES[:shapes_count]

        self.color_key, self.color_rgb, self.color_name = rng.choice(active_colors)
        self.shape_key, self.shape_name = rng.choice(active_shapes)

        if self.rule == "COLOR":
            _, _, target_name = rng.choice(active_colors)
            self.question_text = f"Цвет: это {target_name}?"
            self.answer_is_yes = self.color_name == target_name
            self.spec.payload["target_color"] = target_name
        else:
            _, target_name = rng.choice(active_shapes)
            self.question_text = f"Форма: это {target_name}?"
            self.answer_is_yes = self.shape_name == target_name
            self.spec.payload["target_shape"] = target_name

        self.spec.payload["rule"] = self.rule
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
        bottom_y = ctx.rect.bottom - 24
        center_x = ctx.rect.x + ctx.rect.width // 2
        text_max_w = ctx.rect.width - 32

        rule_label = "ЦВЕТ" if self.rule == "COLOR" else "ФОРМА"
        cue = ctx.font_small.render(f"Правило: {rule_label}", True, ctx.color_main)
        hint_map = ctx.font_small.render("F - да, J - нет", True, ctx.color_main)
        footer = ctx.font_small.render("Ответ по текущему правилу", True, ctx.color_main)

        cursor_y = y + 18
        screen.blit(cue, (x, cursor_y))
        cursor_y += cue.get_height() + 4

        words = self.question_text.split()
        line = ""
        question_lines = []
        for word in words:
            candidate = f"{line} {word}".strip()
            if ctx.font_small.size(candidate)[0] <= text_max_w:
                line = candidate
            else:
                if line:
                    question_lines.append(line)
                line = word
        if line:
            question_lines.append(line)
        for question_line in question_lines:
            q = ctx.font_small.render(question_line, True, ctx.color_main)
            screen.blit(q, (x, cursor_y))
            cursor_y += q.get_height() + 2
        cursor_y += 4

        screen.blit(hint_map, (x, cursor_y))
        cursor_y += hint_map.get_height() + 10

        top_limit = cursor_y
        bottom_limit = bottom_y - footer.get_height() - 8
        shape_area_h = max(44, bottom_limit - top_limit)
        cy = top_limit + shape_area_h // 2
        size = min(ctx.rect.width // 6, shape_area_h // 2 - 4)
        size = max(18, size)

        _draw_shape(screen, self.shape_key, self.color_rgb, center_x, cy, size)

        screen.blit(footer, (x, bottom_y - footer.get_height()))
