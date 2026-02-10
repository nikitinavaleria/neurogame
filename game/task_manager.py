import random
from typing import List, Optional

from config.settings import DifficultyConfig
from data.models import TaskResult, TaskSpec
from game.tasks import CompareCodesTask, RuleSwitchTask, SequenceMemoryTask
from game.tasks.base import TaskBase


class TaskManager:
    def __init__(
        self,
        difficulty: DifficultyConfig,
        total_tasks: int,
        inter_task_pause_ms: int,
        seed: int = 1,
    ) -> None:
        self.difficulty = difficulty
        self.total_tasks = total_tasks
        self.inter_task_pause_ms = inter_task_pause_ms
        self.rng = random.Random(seed)
        self.active_tasks: List[TaskBase] = []
        self.last_spawn_ms: int = 0
        self.next_spawn_after_ms: int = 0
        self.tasks_created: int = 0
        self.tasks_completed: int = 0
        self.current_rule: str = "COLOR"

    def update(self, now_ms: int) -> List[TaskResult]:
        results: List[TaskResult] = []
        for task in list(self.active_tasks):
            task.update(now_ms)
            if task.is_complete():
                results.append(task.get_result())
                self.active_tasks.remove(task)
                self.tasks_completed += 1
                self.next_spawn_after_ms = max(self.next_spawn_after_ms, now_ms + self.inter_task_pause_ms)

        self._spawn_if_needed(now_ms)
        return results

    def handle_event(self, event, now_ms: int):
        focused = self.get_focused_task()
        if focused is not None:
            focused.handle_event(event, now_ms)
            if focused.is_complete():
                self.active_tasks.remove(focused)
                self.tasks_completed += 1
                self.next_spawn_after_ms = max(self.next_spawn_after_ms, now_ms + self.inter_task_pause_ms)
                return focused.get_result()
        return None

    def get_focused_task(self) -> Optional[TaskBase]:
        if not self.active_tasks:
            return None
        return self.active_tasks[0]

    def is_done(self) -> bool:
        return self.tasks_completed >= self.total_tasks

    def _spawn_if_needed(self, now_ms: int) -> None:
        if self.tasks_created >= self.total_tasks:
            return
        if len(self.active_tasks) >= self.difficulty.global_params.parallel_streams:
            return
        interval_ms = int(self.difficulty.global_params.event_rate_sec * 1000)
        if now_ms < self.next_spawn_after_ms:
            return
        if now_ms - self.last_spawn_ms < interval_ms:
            return
        self.last_spawn_ms = now_ms
        self.active_tasks.append(self._create_task(now_ms))
        self.tasks_created += 1

    def set_difficulty(self, difficulty: DifficultyConfig) -> None:
        self.difficulty = difficulty

    def _create_task(self, now_ms: int) -> TaskBase:
        mix = self.difficulty.global_params.task_mix
        roll = self.rng.random()
        if roll < mix[0]:
            return self._create_compare_codes(now_ms)
        if roll < mix[0] + mix[1]:
            return self._create_sequence_memory(now_ms)
        return self._create_rule_switch(now_ms)

    def _create_compare_codes(self, now_ms: int) -> TaskBase:
        diff = self.difficulty.compare
        deadline = now_ms + int(diff.time_limit_ms * self.difficulty.global_params.time_pressure)
        spec = TaskSpec(
            task_id="compare_codes",
            created_ms=now_ms,
            deadline_ms=deadline,
            difficulty={
                "code_len": diff.code_len,
                "similarity_rate": diff.similarity_rate,
                "time_limit_ms": diff.time_limit_ms,
            },
            payload={},
        )
        return CompareCodesTask(spec, self.rng)

    def _create_sequence_memory(self, now_ms: int) -> TaskBase:
        diff = self.difficulty.memory
        deadline = now_ms + int(diff.time_limit_ms * self.difficulty.global_params.time_pressure)
        spec = TaskSpec(
            task_id="sequence_memory",
            created_ms=now_ms,
            deadline_ms=deadline,
            difficulty={
                "seq_len": diff.seq_len,
                "retention_delay_ms": diff.retention_delay_ms,
                "time_limit_ms": diff.time_limit_ms,
            },
            payload={},
        )
        return SequenceMemoryTask(spec, self.rng)

    def _create_rule_switch(self, now_ms: int) -> TaskBase:
        diff = self.difficulty.switch
        if self.rng.random() < diff.rule_switch_rate:
            self.current_rule = "SHAPE" if self.current_rule == "COLOR" else "COLOR"
        deadline = now_ms + int(diff.time_limit_ms * self.difficulty.global_params.time_pressure)
        spec = TaskSpec(
            task_id="rule_switch",
            created_ms=now_ms,
            deadline_ms=deadline,
            difficulty={
                "rule_switch_rate": diff.rule_switch_rate,
                "stimulus_rate_sec": diff.stimulus_rate_sec,
                "time_limit_ms": diff.time_limit_ms,
            },
            payload={"rule": self.current_rule},
        )
        return RuleSwitchTask(spec, self.rng)
