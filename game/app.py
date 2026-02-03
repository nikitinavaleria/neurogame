import statistics
import time
from pathlib import Path
from typing import List

import pygame

from adaptation.baseline import BaselineAdapter, BaselineState
from adaptation.levels import apply_level, apply_tempo
from adaptation.rl_agent import RLAgent
from config.settings import DifficultyConfig, LevelConfig, SessionConfig, WindowConfig
from data.logger import JsonlLogger
from data.models import SessionSummary, TaskResult
from game.task_manager import TaskManager
from game.tasks.base import TaskRenderContext
from game.ui import GameUI


class GameApp:
    def __init__(self, window: WindowConfig, session: SessionConfig, difficulty: DifficultyConfig) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((window.width, window.height))
        pygame.display.set_caption(window.title)
        self.clock = pygame.time.Clock()
        self.ui = GameUI(self.screen)
        self.window = window
        self.session = session
        self.difficulty = difficulty

        self.base_difficulty = difficulty
        self.level_cfg = LevelConfig()
        self.adapter = BaselineAdapter(
            difficulty=self.base_difficulty,
            level_cfg=self.level_cfg,
            state=BaselineState(level=self.level_cfg.start_level, tempo_offset=0),
        )
        self.current_level = self.level_cfg.start_level
        self.tempo_offset = 0
        self.current_difficulty = apply_tempo(
            apply_level(self.base_difficulty, self.current_level), self.tempo_offset
        )
        self.adapt_logger = JsonlLogger("data/adaptations.jsonl")
        self.adapt_step = 0
        self.rl_agent = RLAgent(model_path=session.rl_model_path)
        self.last_adapt_state = None
        self.last_adapt_action = None
        self.last_adapt_reward = None

        self.task_manager = TaskManager(
            self.current_difficulty,
            total_tasks=session.total_tasks,
            inter_task_pause_ms=session.inter_task_pause_ms,
            seed=1,
        )
        self.events_logger = JsonlLogger("data/events.jsonl")
        self.session_logger = JsonlLogger("data/sessions.jsonl")
        self.session_id = f"s{int(time.time())}"
        self.results: List[TaskResult] = []
        self.stability = 1.0
        self.running = True
        self.started = False
        self.last_feedback_ms: int = 0
        self.last_feedback_text: str = ""
        self.last_feedback_ok: bool = True
        self.last_key_ms: int = 0
        self.last_key_text: str = ""
        self.selected_mode = self.session.adaptation_mode

    def run(self) -> None:
        while self.running:
            self.clock.tick(self.window.fps)
            now_ms = pygame.time.get_ticks()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    self.running = False
                if event.type == pygame.KEYDOWN:
                    self.last_key_ms = now_ms
                    name = pygame.key.name(event.key)
                    char = (event.unicode or "").strip()
                    self.last_key_text = f"Клавиша: {name} {f'({char})' if char else ''}"
                if self.started:
                    result = self.task_manager.handle_event(event, now_ms)
                    if result is not None:
                        self._handle_result(result)
                else:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                        self.started = True
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_b:
                        self.selected_mode = "baseline"
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                        self.selected_mode = "ppo"

            if self.started:
                results = self.task_manager.update(now_ms)
                for result in results:
                    self._handle_result(result)

            self._render(now_ms)

            if self.started and self.task_manager.is_done():
                self.running = False

        self._finalize_session()
        pygame.quit()

    def _handle_result(self, result: TaskResult) -> None:
        self.results.append(result)
        self.last_feedback_ms = pygame.time.get_ticks()
        if result.is_timeout:
            self.last_feedback_text = "Слишком поздно"
            self.last_feedback_ok = False
        else:
            self.last_feedback_text = "Ответ принят" if result.correct else "Ошибка"
            self.last_feedback_ok = result.correct
        self.events_logger.write(
            {
                "timestamp": int(time.time()),
                "session_id": self.session_id,
                "task_id": result.task_id,
                "difficulty": result.difficulty,
                "global_difficulty": self._serialize_global_difficulty(),
                "level": self.current_level,
                "adapt_state": self.last_adapt_state,
                "adapt_action": self.last_adapt_action,
                "adapt_reward": self.last_adapt_reward,
                "mode": self.selected_mode,
                "payload": result.payload,
                "response": result.response,
                "correct": int(result.correct),
                "reaction_time": result.rt_ms,
                "deadline_met": int(not result.is_timeout),
            }
        )
        if result.correct:
            self.stability = min(1.0, self.stability + 0.01)
        else:
            self.stability = max(0.0, self.stability - 0.03)

        self._maybe_adapt()

    def _maybe_adapt(self) -> None:
        if len(self.results) < self.level_cfg.window_size:
            return
        if len(self.results) % self.level_cfg.check_every != 0:
            return
        window = self.results[-self.level_cfg.window_size :]
        accuracy = sum(1 for r in window if r.correct) / len(window)
        rts = [r.rt_ms for r in window if r.rt_ms is not None]
        mean_rt = sum(rts) / len(rts) if rts else 0.0
        state = self._build_state(window)
        prev_level = self.current_level
        prev_tempo = self.tempo_offset

        effective_mode = self.selected_mode
        if self.selected_mode == "ppo" and Path(self.session.rl_model_path).exists():
            action_id, delta_level, delta_tempo = self.rl_agent.act(state)
            new_level = max(self.level_cfg.min_level, min(self.level_cfg.max_level, prev_level + delta_level))
            new_tempo = max(-2, min(2, prev_tempo + delta_tempo))
        else:
            new_level, new_tempo = self.adapter.update(accuracy, mean_rt)
            action_id, delta_level, delta_tempo = self._encode_action(prev_level, prev_tempo)
            effective_mode = "baseline"

        self.current_level = new_level
        self.tempo_offset = new_tempo
        self.current_difficulty = apply_tempo(
            apply_level(self.base_difficulty, self.current_level), self.tempo_offset
        )
        self.task_manager.set_difficulty(self.current_difficulty)

        reward = self._compute_reward(accuracy, mean_rt)
        self.last_adapt_state = state
        self.last_adapt_action = action_id
        self.last_adapt_reward = reward

        self.adapt_logger.write(
            {
                "step": self.adapt_step,
                "state": state,
                "action_id": action_id,
                "delta_level": delta_level,
                "delta_tempo": delta_tempo,
                "reward": reward,
                "level": self.current_level,
                "tempo_offset": self.tempo_offset,
                "mode": effective_mode,
            }
        )
        self.adapt_step += 1

    def _render(self, now_ms: int) -> None:
        self.ui.clear()
        self.ui.draw_frame()
        self.ui.draw_title("Deep Space Ops")

        active = self.task_manager.get_active_summary(now_ms)
        focused = self.task_manager.get_focused_task()
        focused_index = None
        if focused is not None:
            focused_index = self.task_manager.active_tasks.index(focused)

        if self.started:
            self.ui.draw_status(
                stability=self.stability,
                load=len(active),
                tasks_done=self.task_manager.tasks_completed,
                total_tasks=self.session.total_tasks,
                level=self.current_level,
            )
            self.ui.draw_task_list(active, focused_index)
            self.ui.draw_footer("F/J или A/O: действие | ESC: выход")
            self._render_task_panels(focused)
            self._render_feedback(now_ms)
            self._render_key_debug(now_ms)
        else:
            self._render_start_screen()

        pygame.display.flip()

    def _render_task_panels(self, focused) -> None:
        panel_map = {
            "compare_codes": (self.ui.task_panels[0], "Сравнение кодов"),
            "sequence_memory": (self.ui.task_panels[1], "Память"),
            "rule_switch": (self.ui.task_panels[2], "Смена правила"),
        }
        active_task_id = focused.spec.task_id if focused is not None else None

        for task_id, (rect, title) in panel_map.items():
            active = task_id == active_task_id
            self.ui.draw_task_panel(rect, title, active)
            if active and focused is not None:
                ctx = TaskRenderContext(
                    rect=rect,
                    font_big=self.ui.font_big,
                    font_mid=self.ui.font_mid,
                    font_small=self.ui.font_small,
                    color_main=self.ui.theme.text,
                    color_accent=self.ui.theme.accent,
                    color_alert=self.ui.theme.alert,
                )
                focused.render(self.screen, ctx)
                self._render_panel_feedback(rect)
            else:
                self._dim_panel(rect)

    def _dim_panel(self, rect: pygame.Rect) -> None:
        overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        overlay.fill((10, 12, 20, 160))
        self.screen.blit(overlay, (rect.x, rect.y))

    def _render_panel_feedback(self, rect: pygame.Rect) -> None:
        now_ms = pygame.time.get_ticks()
        if now_ms - self.last_feedback_ms > 300:
            return
        color = self.ui.theme.accent if self.last_feedback_ok else self.ui.theme.alert
        overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        overlay.fill((*color, 55))
        self.screen.blit(overlay, (rect.x, rect.y))

    def _render_start_screen(self) -> None:
        full = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        full.fill((6, 8, 14, 220))
        self.screen.blit(full, (0, 0))

        box_w = int(self.ui.center_panel.width * 1.35)
        box_h = int(self.ui.center_panel.height * 1.1)
        box_x = (self.ui.w - box_w) // 2
        box_y = (self.ui.h - box_h) // 2
        box = pygame.Rect(box_x, box_y, box_w, box_h)
        pygame.draw.rect(self.screen, self.ui.theme.panel, box, border_radius=12)
        pygame.draw.rect(self.screen, self.ui.theme.border, box, width=2, border_radius=12)

        title = self.ui.font_mid.render("Инструкция", True, self.ui.theme.accent)
        self.screen.blit(title, (box_x + 20, box_y + 16))

        lines = [
            "Ты оператор станции. Внимательно выполняй задачи.",
            "Клавиши: F/J (или A/O) — ответы.",
            "ESC — выход из игры.",
            "",
            "Режим адаптации:",
            f"[B] baseline  |  [R] RL (PPO)  |  текущий: {self.selected_mode}",
            self._rl_warning(),
            "",
            "Задачи:",
            "1) Сравнение кодов: F = совпадает, J = не совпадает.",
            "2) Память: запомни строку, затем F = да, J = нет.",
            "3) Смена правила: смотри правило ЦВЕТ/ФОРМА.",
            "",
            "Нажми ПРОБЕЛ, чтобы начать.",
        ]
        yy = box_y + 50
        for line in lines:
            if line == "Задачи:":
                color = self.ui.theme.accent
            elif line.startswith("Внимание"):
                color = self.ui.theme.alert
            else:
                color = self.ui.theme.text
            surf = self.ui.font_small.render(line, True, color)
            self.screen.blit(surf, (box_x + 20, yy))
            yy += 24

    def _rl_warning(self) -> str:
        if self.selected_mode != "ppo":
            return ""
        if Path(self.session.rl_model_path).exists():
            return ""
        return "Внимание: модель PPO не найдена, будет использован baseline."

    def _render_feedback(self, now_ms: int) -> None:
        if now_ms - self.last_feedback_ms > 350:
            return
        surf = self.ui.font_small.render(self.last_feedback_text, True, self.ui.theme.accent)
        self.screen.blit(surf, (self.ui.center_panel.x + 20, self.ui.center_panel.y + 60))

    def _render_key_debug(self, now_ms: int) -> None:
        if now_ms - self.last_key_ms > 700:
            return
        surf = self.ui.font_small.render(self.last_key_text, True, self.ui.theme.text)
        self.screen.blit(surf, (self.ui.center_panel.x + 20, self.ui.center_panel.y + 90))

    def _finalize_session(self) -> None:
        if not self.results:
            return
        accuracy = sum(1 for r in self.results if r.correct) / len(self.results)
        rts = [r.rt_ms for r in self.results if r.rt_ms is not None]
        mean_rt = statistics.mean(rts) if rts else 0.0
        rt_variance = statistics.pvariance(rts) if len(rts) > 1 else 0.0
        summary = SessionSummary(
            session_id=self.session_id,
            total_tasks=len(self.results),
            accuracy_total=accuracy,
            mean_rt=mean_rt,
            rt_variance=rt_variance,
            switch_cost=0.0,
            fatigue_trend=0.0,
            overload_events=0,
        )
        self.session_logger.write(summary.__dict__)

    def _serialize_global_difficulty(self) -> dict:
        g = self.current_difficulty.global_params
        return {
            "event_rate_sec": g.event_rate_sec,
            "parallel_streams": g.parallel_streams,
            "time_pressure": g.time_pressure,
            "task_mix": g.task_mix,
        }

    def _encode_action(self, prev_level: int, prev_tempo: int) -> tuple:
        delta_level = max(-1, min(1, self.current_level - prev_level))
        delta_tempo = max(-1, min(1, self.tempo_offset - prev_tempo))
        action_id = (delta_level + 1) * 3 + (delta_tempo + 1)
        return action_id, delta_level, delta_tempo

    def _build_state(self, window: List[TaskResult]) -> list:
        acc = sum(1 for r in window if r.correct) / len(window)
        rts = [r.rt_ms for r in window if r.rt_ms is not None]
        mean_rt = sum(rts) / len(rts) if rts else 0.0
        std_rt = 0.0
        if len(rts) > 1:
            mean = mean_rt
            std_rt = (sum((x - mean) ** 2 for x in rts) / len(rts)) ** 0.5

        error_streak = 0
        for r in reversed(window):
            if r.correct:
                break
            error_streak += 1

        switch_cost = self._compute_switch_cost(window)
        fatigue_trend = self._compute_fatigue_trend(window)
        g = self.current_difficulty.global_params
        return [
            acc,
            mean_rt,
            std_rt,
            float(error_streak),
            switch_cost,
            fatigue_trend,
            float(self.current_level),
            g.event_rate_sec,
            g.time_pressure,
            float(g.parallel_streams),
            float(g.task_mix[0]),
            float(g.task_mix[1]),
        ]

    @staticmethod
    def _compute_reward(acc: float, mean_rt: float) -> float:
        reward = acc - 0.7
        if mean_rt > 1000:
            reward -= 0.0004 * (mean_rt - 1000)
        return reward

    @staticmethod
    def _compute_fatigue_trend(window: List[TaskResult]) -> float:
        rts = [r.rt_ms for r in window if r.rt_ms is not None]
        if len(rts) < 2:
            return 0.0
        n = len(rts)
        xs = list(range(n))
        mean_x = (n - 1) / 2
        mean_y = sum(rts) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, rts))
        den = sum((x - mean_x) ** 2 for x in xs) or 1.0
        return num / den

    @staticmethod
    def _compute_switch_cost(window: List[TaskResult]) -> float:
        switch_rts = []
        nonswitch_rts = []
        prev_rule = None
        for r in window:
            if r.task_id != "rule_switch":
                continue
            rule = r.payload.get("rule")
            if rule is None or r.rt_ms is None:
                continue
            if prev_rule is not None and rule != prev_rule:
                switch_rts.append(r.rt_ms)
            else:
                nonswitch_rts.append(r.rt_ms)
            prev_rule = rule
        if not switch_rts or not nonswitch_rts:
            return 0.0
        return (sum(switch_rts) / len(switch_rts)) - (sum(nonswitch_rts) / len(nonswitch_rts))
