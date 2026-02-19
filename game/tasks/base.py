from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import pygame

from game.runtime.models import TaskResult, TaskSpec


@dataclass
class TaskRenderContext:
    rect: pygame.Rect
    font_big: pygame.font.Font
    font_mid: pygame.font.Font
    font_small: pygame.font.Font
    color_main: Tuple[int, int, int]
    color_accent: Tuple[int, int, int]
    color_alert: Tuple[int, int, int]


class TaskBase:
    task_id: str = "BASE"

    def __init__(self, spec: TaskSpec) -> None:
        self.spec = spec
        self.created_ms = spec.created_ms
        self.deadline_ms = spec.deadline_ms
        self.finished_ms: Optional[int] = None
        self.response: Optional[str] = None
        self.correct: bool = False
        self.is_timeout: bool = False

    def handle_event(self, event: pygame.event.Event, now_ms: int) -> None:
        raise NotImplementedError

    def update(self, now_ms: int) -> None:
        if self.finished_ms is not None:
            return
        if now_ms >= self.deadline_ms:
            self.is_timeout = True
            self.finished_ms = now_ms

    def render(self, screen: pygame.Surface, ctx: TaskRenderContext) -> None:
        raise NotImplementedError

    def is_complete(self) -> bool:
        return self.finished_ms is not None

    def get_result(self) -> TaskResult:
        rt_ms = None
        if self.finished_ms is not None:
            rt_ms = self.finished_ms - self.created_ms
        return TaskResult(
            task_id=self.spec.task_id,
            created_ms=self.created_ms,
            finished_ms=self.finished_ms or self.created_ms,
            response=self.response,
            correct=self.correct,
            rt_ms=rt_ms,
            is_timeout=self.is_timeout,
            difficulty=self.spec.difficulty,
            payload=self.spec.payload,
        )
