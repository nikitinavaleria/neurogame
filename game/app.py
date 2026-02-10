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
        self.stability = 0.0
        self.running = True
        self.started = False
        self.last_feedback_ms: int = 0
        self.last_feedback_text: str = ""
        self.last_feedback_ok: bool = True
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
                if self.started:
                    result = self.task_manager.handle_event(event, now_ms)
                    if result is not None:
                        self._handle_result(result)
                else:
                    if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                        self.started = True
                    if event.type == pygame.KEYDOWN and (
                        event.key == pygame.K_b or (event.unicode or "").lower() == "в"
                    ):
                        if self.selected_mode == "baseline":
                            if Path(self.session.rl_model_path).exists():
                                self.selected_mode = "ppo"
                        else:
                            self.selected_mode = "baseline"

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

        focused = self.task_manager.get_focused_task()
        focused_name = None
        focused_time_left = None
        if focused is not None:
            focused_name = self._task_title(focused.spec.task_id)
            focused_time_left = max(0, focused.spec.deadline_ms - now_ms)
        show_timeout_alert = self.last_feedback_text == "Слишком поздно" and now_ms - self.last_feedback_ms <= 900

        if self.started:
            self.ui.draw_title("Deep Space Ops")
            self.ui.draw_status(
                stability=self.stability,
                tasks_done=self.task_manager.tasks_completed,
                total_tasks=self.session.total_tasks,
                level=self.current_level,
            )
            self.ui.draw_focus_panel(focused_name, focused_time_left, show_timeout_alert)
            self.ui.draw_help_panel()
            self._render_task_panels(focused)
            self._render_feedback(now_ms)
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

        title_shadow = self.ui.font_big.render("Deep Space Ops", True, (12, 20, 40))
        title_main = self.ui.font_big.render("Deep Space Ops", True, self.ui.theme.accent)
        title_rect = title_main.get_rect(center=(self.ui.w // 2, 48))
        self.screen.blit(title_shadow, (title_rect.x + 2, title_rect.y + 2))
        self.screen.blit(title_main, title_rect)

        main_top = 84
        main_bottom = self.ui.h - 20
        main_height = max(240, main_bottom - main_top)

        left_box = pygame.Rect(
            self.ui.left_panel.x,
            main_top,
            self.ui.left_panel.width,
            main_height,
        )
        center_box = pygame.Rect(
            self.ui.center_panel.x,
            main_top,
            self.ui.center_panel.width,
            main_height,
        )
        right_full_box = pygame.Rect(
            self.ui.right_panel.x,
            main_top,
            self.ui.right_panel.width,
            main_height,
        )
        right_gap = 14
        right_top_h = (right_full_box.height - right_gap) // 2
        right_top_box = pygame.Rect(
            right_full_box.x,
            right_full_box.y,
            right_full_box.width,
            right_top_h,
        )
        right_bottom_box = pygame.Rect(
            right_full_box.x,
            right_top_box.bottom + 14,
            right_full_box.width,
            right_full_box.height - right_top_h - right_gap,
        )

        for rect in [center_box, left_box, right_top_box, right_bottom_box]:
            pygame.draw.rect(self.screen, self.ui.theme.panel, rect, border_radius=12)
            pygame.draw.rect(self.screen, self.ui.theme.border, rect, width=2, border_radius=12)

        title = self.ui.font_mid.render("Инструкция", True, self.ui.theme.accent)
        self.screen.blit(title, (center_box.x + 20, center_box.y + 16))

        center_lines = [
            "Ты - оператор космической станции.",
            "Внимательно выполняй задачи,",
            "ведь именно от тебя зависит успех операции...",
            "",
            "Нажми ПРОБЕЛ, чтобы начать",
        ]
        yy = center_box.y + 56
        for line in center_lines:
            surf = self.ui.font_small.render(line, True, self.ui.theme.text)
            self.screen.blit(surf, (center_box.x + 20, yy))
            yy += 24

        mode_title = self.ui.font_small.render("Текущий режим адаптации:", True, self.ui.theme.accent)
        self.screen.blit(mode_title, (right_top_box.x + 16, right_top_box.y + 16))
        mode_label = "базовый" if self.selected_mode == "baseline" else "адаптивный"
        mode_value = self.ui.font_mid.render(mode_label, True, self.ui.theme.text)
        self.screen.blit(mode_value, (right_top_box.x + 16, right_top_box.y + 50))
        switch_label = self.ui.font_small.render("Сменить: В", True, self.ui.theme.text)
        self.screen.blit(switch_label, (right_top_box.x + 16, right_top_box.y + 88))

        warning = self._rl_warning()
        if warning:
            warning_surf = self.ui.font_tiny.render(warning, True, self.ui.theme.alert)
            self.screen.blit(warning_surf, (right_top_box.x + 16, right_top_box.y + 120))

        rules_title = self.ui.font_small.render("Правила игры:", True, self.ui.theme.accent)
        self.screen.blit(rules_title, (right_bottom_box.x + 16, right_bottom_box.y + 16))
        rules_lines = [
            "Нажимай на клавиши F/J",
            "для ответов на вопросы",
            "Нажимай на ESC,",
            "если хочешь покинуть игру",
        ]
        yy = right_bottom_box.y + 48
        for line in rules_lines:
            surf = self.ui.font_small.render(line, True, self.ui.theme.text)
            self.screen.blit(surf, (right_bottom_box.x + 16, yy))
            yy += 24

        tasks_title = self.ui.font_small.render("Задачи", True, self.ui.theme.accent)
        self.screen.blit(tasks_title, (left_box.x + 16, left_box.y + 16))
        task_lines = [
            "1. Сравнение кодов",
            "2. Память последовательностей",
            "3. Переключение правил",
        ]
        yy = left_box.y + 48
        for line in task_lines:
            surf = self.ui.font_small.render(line, True, self.ui.theme.text)
            self.screen.blit(surf, (left_box.x + 16, yy))
            yy += 24

    def _rl_warning(self) -> str:
        if Path(self.session.rl_model_path).exists():
            return ""
        return "Агент не доступен, смена невозможна"

    def _render_feedback(self, now_ms: int) -> None:
        if now_ms - self.last_feedback_ms > 500:
            return
        if self.last_feedback_text == "Слишком поздно":
            return
        color = self.ui.theme.accent if self.last_feedback_ok else self.ui.theme.alert
        shadow = self.ui.font_big.render(self.last_feedback_text, True, (10, 16, 28))
        text = self.ui.font_big.render(self.last_feedback_text, True, color)
        rect = text.get_rect(center=self.ui.center_panel.center)
        self.screen.blit(shadow, (rect.x + 2, rect.y + 2))
        self.screen.blit(text, rect)

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

    @staticmethod
    def _task_title(task_id: str) -> str:
        return {
            "compare_codes": "Сравнение кодов",
            "sequence_memory": "Память",
            "rule_switch": "Смена правила",
        }.get(task_id, task_id)

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
