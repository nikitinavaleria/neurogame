import statistics
import time
import random
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Dict, List

import pygame

from game.adaptation.baseline import BaselineAdapter, BaselineState
from game.adaptation.levels import apply_level, apply_task_offsets, apply_tempo
from game.adaptation.rl_agent import RLAgent
from game.settings import DifficultyConfig, LevelConfig, SessionConfig, WindowConfig
from game.runtime.auth import UserAuthStore
from game.runtime.logger import JsonlLogger
from game.runtime.models import SessionSummary, TaskResult
from game.runtime.pending_runs_store import (
    load_pending_runs as load_pending_runs_file,
    save_pending_runs as save_pending_runs_file,
)
from game.runtime.paths import app_data_path, bundled_data_path, bundled_resource_path
from game.runtime.telemetry_settings import (
    load_telemetry_settings as load_telemetry_settings_file,
    save_telemetry_settings as save_telemetry_settings_file,
)
from game.runtime.telemetry_client import TelemetryClient
from game.input_handlers import (
    handle_auth_event,
    handle_auth_mouse,
    handle_menu_mouse,
    handle_pause_menu_mouse,
    handle_telemetry_event,
)
from game.session_metrics import (
    build_state_vector,
    compute_flight_progress,
    compute_fatigue_trend,
    compute_zone_quality,
    compute_reward,
    compute_switch_cost,
    count_successes,
    task_title,
)
from game.task_manager import TaskManager
from game.tasks.base import TaskRenderContext
from game.ui import GameUI


class GameApp:
    def __init__(self, window: WindowConfig, session: SessionConfig, difficulty: DifficultyConfig) -> None:
        pygame.init()
        self.display_flags = pygame.RESIZABLE | pygame.DOUBLEBUF
        initial_size = self._pick_initial_window_size(window.width, window.height)
        self.screen = pygame.display.set_mode(initial_size, self.display_flags, vsync=1)
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
        self.task_offsets: Dict[str, int] = self._empty_task_offsets()
        self.current_difficulty = self._build_effective_difficulty()
        self.events_log_path = app_data_path("events.jsonl")
        self.adapt_log_path = app_data_path("adaptations.jsonl")
        self.session_log_path = app_data_path("sessions.jsonl")
        self.users_path = app_data_path("users.json")
        self.pending_runs_path = app_data_path("pending_runs.json")
        self.telemetry_queue_path = app_data_path("telemetry_queue.jsonl")
        self.telemetry_settings_path = app_data_path("telemetry_settings.json")
        self.error_log_path = app_data_path("client_errors.log")
        self.default_telemetry_url = os.getenv(
            "NEUROGAME_DEFAULT_TELEMETRY_URL",
            os.getenv("NEUROGAME_TELEMETRY_URL", "http://127.0.0.1:8000/v1/events"),
        ).strip()
        telemetry_url, telemetry_api_key = self._load_telemetry_settings()
        self.telemetry_url_value = telemetry_url
        self.telemetry_api_key_value = telemetry_api_key
        self.telemetry_status_message: str = ""
        self.telemetry_status_ok: bool = False
        self.adapt_logger = JsonlLogger(str(self.adapt_log_path))
        self.adapt_step = 0
        self.rl_model_path = self._resolve_resource_path(session.rl_model_path)
        self.rl_agent = RLAgent(model_path=str(self.rl_model_path))
        self.last_adapt_state = None
        self.last_adapt_action = None
        self.last_adapt_reward = None

        self.task_manager = TaskManager(
            self.current_difficulty,
            total_tasks=session.total_tasks,
            inter_task_pause_ms=session.inter_task_pause_ms,
            seed=1,
        )
        self.task_manager.set_level(self.current_level)
        self.events_logger = JsonlLogger(str(self.events_log_path))
        self.session_logger = JsonlLogger(str(self.session_log_path))
        self.telemetry = TelemetryClient(
            endpoint_url=self.telemetry_url_value,
            api_key=self.telemetry_api_key_value,
            client_version=os.getenv("NEUROGAME_CLIENT_VERSION", "game-dev"),
            queue_path=str(self.telemetry_queue_path),
        )
        self.session_id = f"s{int(time.time())}"
        self.results: List[TaskResult] = []
        self.stability = 0.0
        self.running = True
        self.started = False
        self.last_feedback_ms: int = 0
        self.last_feedback_text: str = ""
        self.last_feedback_ok: bool = True
        self.last_feedback_duration_ms: int = 1200
        self.last_feedback_task_id: str | None = None
        self.last_feedback_slot_index: int | None = None
        self.active_slot_index: int | None = None
        self.last_focused_token: int | None = None
        self.slot_rng = random.Random()
        self.batch_result_start: int = 0
        self.batch_index: int = 1
        self.planets_visited: int = 0
        self.selected_mode = self.session.adaptation_mode
        # TEMP: for the second testing phase we route both UI modes to the model policy.
        # The toggle remains visible for users, but the effective runtime mode is forced to PPO.
        self.force_model_mode: bool = True
        self.auth_store = UserAuthStore(
            str(self.users_path),
            endpoint_url=self.telemetry_url_value,
            api_key=self.telemetry_api_key_value,
        )
        self.user_id: str | None = None
        self.authenticated: bool = False
        self.auth_mode: str = "login"
        self.auth_username: str = ""
        self.auth_password: str = ""
        self.auth_focus: str = "username"
        self.auth_message: str = ""
        self.user_progress: Dict[str, float] = self._empty_progress()
        self.user_recent_sessions: List[dict] = []
        self.motivation_phrases: List[str] = [
            "Молчи громче, чем другие кричат - результат всё объяснит.",
            "Сначала работа над собой, потом - разговоры о судьбе.",
            "Хочешь уважения? Сделай так, чтобы без тебя было хуже.",
            "Страх - это сигнал. Слабость - это выбор.",
            "Не трать время на оправдания - трать его на прогресс.",
            "Чем тише шаги, тем громче финиш.",
            "Либо ты управляешь днём, либо день управляет тобой.",
            "Упорство бьёт талант, если талант ленится.",
            "Не обещай - докажи.",
            "Пока другие ищут причины, ты ищи способы.",
            "Дисциплина сегодня - свобода завтра.",
            "Сильный не тот, кто не падает, а тот, кто поднимается быстрее.",
            "Делай так, чтобы сомневающиеся запоминали твоё имя.",
            "Устал - не значит проиграл. Это значит, что идёшь дальше остальных.",
            "Настоящий риск - прожить жизнь вполсилы.",
            "Если цель пугает - значит, она стоит того.",
            "Не соревнуйся с людьми - соревнуйся со вчерашним собой.",
            "Спокойствие - оружие тех, кто уверен в ударе.",
            "Дорога тяжёлая? Значит, ты идёшь вверх.",
            "Твоё будущее начинается с решений, которые ты принимаешь сегодня.",
        ]
        self.current_motivation_phrase: str = self.motivation_phrases[0]
        self._roll_motivation_phrase()
        self.auth_card_rect: pygame.Rect | None = None
        self.auth_username_rect: pygame.Rect | None = None
        self.auth_password_rect: pygame.Rect | None = None
        self.auth_submit_rect: pygame.Rect | None = None
        self.auth_toggle_rect: pygame.Rect | None = None
        self.start_button_rect: pygame.Rect | None = None
        self.resume_button_rect: pygame.Rect | None = None
        self.restart_button_rect: pygame.Rect | None = None
        self.menu_button_rect: pygame.Rect | None = None
        self.exit_button_rect: pygame.Rect | None = None
        self.mode_toggle_rect: pygame.Rect | None = None
        self.logout_button_rect: pygame.Rect | None = None
        self.telemetry_url_rect: pygame.Rect | None = None
        self.telemetry_save_rect: pygame.Rect | None = None
        self.telemetry_check_rect: pygame.Rect | None = None
        self.telemetry_input_focused: bool = False
        self.awaiting_run_setup: bool = True
        self.pause_between_levels: bool = True
        self.level_transition_toggle_rect: pygame.Rect | None = None
        self.instructions_button_rect: pygame.Rect | None = None
        self.instructions_start_rect: pygame.Rect | None = None
        self.instructions_close_rect: pygame.Rect | None = None
        self.max_level_continue_rect: pygame.Rect | None = None
        self.max_level_menu_rect: pygame.Rect | None = None
        self.pause_menu_open: bool = False
        self.instructions_open: bool = False
        self.instructions_completed: bool = False
        self.instructions_launch_action: str | None = None
        self.max_level_popup_open: bool = False
        self.persist_active_run_on_exit: bool = False
        self.partial_session_end_emitted: bool = False
        self.saved_run_preview_stats: Dict[str, float] | None = None
        self.task_struggle_streak: int = 0
        self.task_flow_streak: int = 0
        self.last_task_adjustment_reason: str = "neutral"

    @staticmethod
    def _pick_initial_window_size(target_w: int, target_h: int) -> tuple[int, int]:
        info = pygame.display.Info()
        display_w = int(getattr(info, "current_w", target_w) or target_w)
        display_h = int(getattr(info, "current_h", target_h) or target_h)
        min_w, min_h = 760, 520
        max_w = max(min_w, int(display_w * 0.96))
        max_h = max(min_h, int(display_h * 0.92))
        width = max(min_w, min(int(target_w), max_w))
        height = max(min_h, min(int(target_h), max_h))
        return width, height

    def _apply_window_resize(self, width: int, height: int) -> None:
        new_w = max(760, int(width))
        new_h = max(520, int(height))
        self.screen = pygame.display.set_mode((new_w, new_h), self.display_flags, vsync=1)
        self.ui = GameUI(self.screen)

    def run(self) -> None:
        while self.running:
            self.clock.tick(self.window.fps)
            now_ms = pygame.time.get_ticks()

            for event in pygame.event.get():
                if event.type == pygame.VIDEORESIZE:
                    self._apply_window_resize(event.w, event.h)
                    continue
                if event.type == pygame.QUIT:
                    if self._has_resumable_run():
                        self._emit_partial_session_end(reason="window_close")
                        self._save_active_run_snapshot()
                        self.persist_active_run_on_exit = True
                    self.running = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if self.instructions_open:
                        self._close_instructions()
                    elif self.max_level_popup_open:
                        self._continue_after_max_level_popup()
                    elif self.started:
                        self._pause_run(open_pause_menu=True)
                    elif self.pause_menu_open:
                        self.started = True
                        self.pause_menu_open = False
                        self.telemetry.track(
                            event_type="session_resume",
                            user_id=self.user_id,
                            session_id=self.session_id,
                            model_version=self._model_version(),
                            payload={
                                "session_id": self.session_id,
                                "user_id": self.user_id,
                                "mode": self._effective_mode(),
                                "source": "escape",
                            },
                        )
                    continue
                if self.started:
                    result = self.task_manager.handle_event(event, now_ms)
                    if result is not None:
                        self._handle_result(result)
                else:
                    if self.max_level_popup_open:
                        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                            self._continue_after_max_level_popup()
                            continue
                        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                            self._handle_max_level_popup_mouse(event.pos)
                        continue
                    if self.instructions_open:
                        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                            self._complete_instructions()
                            continue
                        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                            self._handle_instructions_mouse(event.pos)
                        continue
                    if not self.authenticated:
                        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                            self._handle_auth_mouse(event.pos)
                        self._handle_auth_event(event)
                    else:
                        if self._handle_telemetry_event(event):
                            continue
                        if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_RETURN):
                            if self.awaiting_run_setup:
                                if self._has_saved_run_for_user():
                                    if self.instructions_completed:
                                        if self._restore_saved_run():
                                            continue
                                    else:
                                        self._open_instructions(launch_action="resume_saved")
                                        continue
                                start_level = int(self.user_progress.get("last_level", 1)) if self.user_progress.get("sessions", 0) > 0 else 1
                                if not self.instructions_completed:
                                    launch_action = "resume_level" if self.user_progress.get("sessions", 0) > 0 else "start_new"
                                    self._open_instructions(launch_action=launch_action)
                                    continue
                                self._begin_user_run(max(1, start_level))
                            else:
                                if self.instructions_completed:
                                    self.started = True
                                else:
                                    self._open_instructions(launch_action="continue_active")
                        if event.type == pygame.KEYDOWN and (
                            event.key in (pygame.K_b, pygame.K_r) or (event.unicode or "").lower() in ("в", "r")
                        ):
                            if self.pause_menu_open:
                                continue
                            if self.selected_mode == "baseline":
                                if self._rl_model_exists():
                                    self.selected_mode = "ppo"
                            else:
                                self.selected_mode = "baseline"
                        if event.type == pygame.KEYDOWN and (
                            event.key == pygame.K_t or (event.unicode or "").lower() in ("е", "t")
                        ):
                            if self.pause_menu_open:
                                continue
                            self.pause_between_levels = not self.pause_between_levels
                        if event.type == pygame.KEYDOWN and event.key == pygame.K_l:
                            if not self.pause_menu_open:
                                self._logout_user()
                        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                            if self.pause_menu_open:
                                self._handle_pause_menu_mouse(event.pos)
                            else:
                                self._handle_menu_mouse(event.pos)

            if self.started:
                results = self.task_manager.update(now_ms)
                for result in results:
                    self._handle_result(result)

            self.telemetry.flush()
            self._render(now_ms)

            if self.started and self.task_manager.is_done():
                self._start_next_batch()

        self._finalize_session()
        self.telemetry.flush(force=True)
        pygame.quit()

    def _handle_result(self, result: TaskResult) -> None:
        self.results.append(result)
        self.last_feedback_ms = pygame.time.get_ticks()
        self.last_feedback_duration_ms = 1200
        self.last_feedback_task_id = result.task_id
        self.last_feedback_slot_index = self.active_slot_index
        if result.is_timeout:
            self.last_feedback_text = "Слишком поздно"
            self.last_feedback_ok = False
        else:
            self.last_feedback_text = "Ответ принят" if result.correct else "Ошибка"
            self.last_feedback_ok = result.correct
        event_record = {
            "timestamp": int(time.time()),
            "session_id": self.session_id,
            "user_id": self.user_id,
            "batch_index": self.batch_index,
            "batch_task_index": self.task_manager.tasks_completed,
            "task_id": result.task_id,
            "difficulty": result.difficulty,
            "global_difficulty": self._serialize_global_difficulty(),
            "level": self.current_level,
            "adapt_state": self.last_adapt_state,
            "adapt_action": self.last_adapt_action,
            "adapt_reward": self.last_adapt_reward,
            "mode": self._effective_mode(),
            "payload": result.payload,
            "response": result.response,
            "correct": int(result.correct),
            "reaction_time": result.rt_ms,
            "deadline_met": int(not result.is_timeout),
        }
        self.events_logger.write(event_record)
        self.telemetry.track(
            event_type="task_result",
            user_id=self.user_id,
            session_id=self.session_id,
            model_version=self._model_version(),
            payload=event_record,
        )
        if result.correct:
            self.stability = min(1.0, self.stability + 0.01)
        else:
            self.stability = max(0.0, self.stability - 0.03)
        self._save_active_run_snapshot()

    def _maybe_adapt(self, batch: List[TaskResult]) -> None:
        if not batch:
            return

        # Адаптация теперь привязана к завершению батча (этапа),
        # чтобы совпадать с новой логикой уровня/паузы между уровнями.
        window_size = min(len(batch), self.level_cfg.window_size)
        window = batch[-window_size:]
        accuracy = sum(1 for r in window if r.correct) / len(window)
        rts = [r.rt_ms for r in window if r.rt_ms is not None]
        mean_rt = sum(rts) / len(rts) if rts else 0.0
        state = self._build_state(window)
        prev_level = self.current_level
        prev_tempo = self.tempo_offset

        effective_mode = self._effective_mode()
        if effective_mode == "ppo" and self._rl_model_exists():
            _, _, delta_tempo = self.rl_agent.act(state)
            new_level = prev_level
            new_tempo = self._clamp_tempo_for_level(prev_tempo + delta_tempo, prev_level)
            self._apply_task_deltas(self.rl_agent.last_task_deltas or {})
            self._apply_task_offset_adaptation(state)
            action_id = delta_tempo + 1
            delta_level = 0
        else:
            # Baseline intentionally stays neutral to make PPO gains observable:
            # no dynamic tempo policy and no task-level personalization.
            new_tempo = 0
            new_level = prev_level
            self.adapter.state.level = prev_level
            new_tempo = self._clamp_tempo_for_level(new_tempo, prev_level)
            delta_tempo = max(-1, min(1, new_tempo - prev_tempo))
            self._relax_task_offsets_to_neutral()
            action_id = delta_tempo + 1
            delta_level = 0
            effective_mode = "baseline"

        self.current_level = new_level
        self.tempo_offset = new_tempo
        self.current_difficulty = self._build_effective_difficulty()
        self.task_manager.set_difficulty(self.current_difficulty)
        self.task_manager.set_level(self.current_level)

        reward = self._compute_reward(accuracy, mean_rt)
        self.last_adapt_state = state
        self.last_adapt_action = action_id
        self.last_adapt_reward = reward

        adaptation_record = {
            "step": self.adapt_step,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "batch_index": self.batch_index,
            "batch_tasks_completed": self.task_manager.tasks_completed,
            "state": state,
            "action_id": action_id,
            "delta_level": delta_level,
            "delta_tempo": delta_tempo,
            "reward": reward,
            "level": self.current_level,
            "tempo_offset": self.tempo_offset,
            "mode": effective_mode,
            "action_space": "tempo3_task_offsets_v1",
            "task_offsets": dict(self.task_offsets),
            "task_adjustment_reason": self.last_task_adjustment_reason,
        }
        self.adapt_logger.write(adaptation_record)
        self.telemetry.track(
            event_type="adaptation_step",
            user_id=self.user_id,
            session_id=self.session_id,
            model_version=f"{effective_mode}_v1",
            payload=adaptation_record,
        )
        self.adapt_step += 1

    def _render(self, now_ms: int) -> None:
        self.ui.clear()
        if self.started or self.authenticated:
            self.ui.draw_frame()

        focused = self.task_manager.get_focused_task()
        focused_name = None
        focused_time_left = None
        if focused is not None:
            focused_name = self._task_title(focused.spec.task_id)
            focused_time_left = max(0, focused.spec.deadline_ms - now_ms)
        show_timeout_alert = self.last_feedback_text == "Слишком поздно" and now_ms - self.last_feedback_ms <= 900

        if self.started:
            total_planets = self._total_planets_overall()
            self.ui.draw_title("Deep Space Ops")
            self.ui.draw_status(
                stability=self.stability,
                tasks_done=self.task_manager.tasks_completed,
                total_tasks=self.session.total_tasks,
                level=self.current_level,
                planets_visited=total_planets,
            )
            self.ui.draw_focus_panel(focused_name, focused_time_left, show_timeout_alert)
            self.ui.draw_help_panel()
            answered = self._current_flight_successes()
            self.ui.draw_mission_panel(
                flight_progress=self._current_flight_progress(),
                zone_quality=self._current_zone_quality(),
                tasks_done=answered,
                total_tasks=self.session.total_tasks,
                planets_visited=total_planets,
            )
            self._render_task_panels(focused)
            self._render_feedback(now_ms)
        else:
            if self.max_level_popup_open:
                self._render_paused_scene()
                self._render_max_level_popup()
            elif self.pause_menu_open:
                self._render_paused_scene()
                self._render_pause_menu()
            else:
                self._render_start_screen()
            if self.instructions_open:
                self._render_instructions_overlay()

        pygame.display.flip()

    def _render_task_panels(self, focused) -> None:
        if focused is not None:
            focused_token = id(focused)
            if focused_token != self.last_focused_token:
                self.last_focused_token = focused_token
                self.active_slot_index = self.slot_rng.randrange(len(self.ui.task_panels))
        else:
            self.active_slot_index = None
            self.last_focused_token = None

        for idx, rect in enumerate(self.ui.task_panels):
            active = focused is not None and idx == self.active_slot_index
            title = self._task_title(focused.spec.task_id) if active and focused is not None else "Ожидание"
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
                try:
                    focused.render(self.screen, ctx)
                except Exception as exc:  # noqa: BLE001
                    self._handle_runtime_error("task_render", exc)
            else:
                self._dim_panel(rect)
            self._render_panel_feedback(rect, idx)

    def _render_paused_scene(self) -> None:
        total_planets = self._total_planets_overall()
        self.ui.draw_title("Deep Space Ops")
        self.ui.draw_status(
            stability=self.stability,
            tasks_done=self.task_manager.tasks_completed,
            total_tasks=self.session.total_tasks,
            level=self.current_level,
            planets_visited=total_planets,
        )
        self.ui.draw_focus_panel(None, None, False)
        self.ui.draw_help_panel()
        answered = self._current_flight_successes()
        self.ui.draw_mission_panel(
            flight_progress=self._current_flight_progress(),
            zone_quality=self._current_zone_quality(),
            tasks_done=answered,
            total_tasks=self.session.total_tasks,
            planets_visited=total_planets,
        )
        self._render_task_panels(self.task_manager.get_focused_task())

    def _render_pause_menu(self) -> None:
        self.start_button_rect = None
        self.resume_button_rect = None
        self.restart_button_rect = None
        self.menu_button_rect = None
        self.mode_toggle_rect = None
        self.level_transition_toggle_rect = None
        self.instructions_button_rect = None
        self.max_level_continue_rect = None
        self.max_level_menu_rect = None

        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((6, 8, 14, 220))
        self.screen.blit(overlay, (0, 0))

        card_w = min(520, self.ui.w - 80)
        card_h = 350
        card = pygame.Rect(0, 0, card_w, card_h)
        card.center = (self.ui.w // 2, self.ui.h // 2)
        pygame.draw.rect(self.screen, (20, 28, 44), card, border_radius=14)
        pygame.draw.rect(self.screen, self.ui.theme.accent, card, width=2, border_radius=14)

        title = self.ui.font_mid.render("Пауза", True, self.ui.theme.accent)
        self.screen.blit(title, (card.x + 20, card.y + 18))

        btn_w = card.width - 40
        self.resume_button_rect = pygame.Rect(card.x + 20, card.y + 66, btn_w, 42)
        self.menu_button_rect = pygame.Rect(card.x + 20, card.y + 116, btn_w, 42)
        self.restart_button_rect = pygame.Rect(card.x + 20, card.y + 166, btn_w, 42)
        self.logout_button_rect = pygame.Rect(card.x + 20, card.y + 216, btn_w, 42)
        self.exit_button_rect = pygame.Rect(card.x + 20, card.y + 266, btn_w, 42)
        self.ui.draw_button(self.resume_button_rect, "Продолжить", active=True)
        self.ui.draw_button(self.menu_button_rect, "В главное меню", active=False)
        self.ui.draw_button(self.restart_button_rect, "Начать заново", active=False)
        self.ui.draw_button(self.logout_button_rect, "Сменить пользователя", active=False)
        self.ui.draw_button(self.exit_button_rect, "Выход из приложения", active=False)
        hint = self.ui.font_tiny.render("Esc - продолжить", True, self.ui.theme.text)
        self.screen.blit(hint, (card.x + 20, card.bottom - 30))

    def _render_max_level_popup(self) -> None:
        self.start_button_rect = None
        self.resume_button_rect = None
        self.restart_button_rect = None
        self.menu_button_rect = None
        self.mode_toggle_rect = None
        self.level_transition_toggle_rect = None
        self.instructions_button_rect = None

        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((6, 8, 14, 228))
        self.screen.blit(overlay, (0, 0))

        card_w = min(760, self.ui.w - 80)
        card_h = min(420, self.ui.h - 80)
        card = pygame.Rect(0, 0, card_w, card_h)
        card.center = (self.ui.w // 2, self.ui.h // 2)
        pygame.draw.rect(self.screen, (20, 28, 44), card, border_radius=16)
        pygame.draw.rect(self.screen, self.ui.theme.accent, card, width=2, border_radius=16)

        title = self.ui.font_mid.render("Максимальный уровень", True, self.ui.theme.accent)
        title_rect = title.get_rect(center=(card.centerx, card.y + 38))
        self.screen.blit(title, title_rect)

        body_lines = [
            "Ура! Вы достигли максимального уровня, поздравляем!",
            "",
            "Продолжайте играть как можно больше,",
            "чтобы тренировать ваши когнитивные способности",
            "(и чтобы Лера набрала классы на дипломе).",
            "",
            "Когда закончите игру - не забудьте закрыть приложение.",
            "Ищите себя в лидерборде.",
        ]
        line_h = self.ui.font_small.get_height() + 8
        body_top = card.y + 86
        for idx, line in enumerate(body_lines):
            if not line:
                continue
            surf = self.ui.font_small.render(line, True, self.ui.theme.text)
            surf_rect = surf.get_rect(center=(card.centerx, body_top + idx * line_h))
            self.screen.blit(surf, surf_rect)

        btn_w = (card.width - 58) // 2
        btn_y = card.bottom - 72
        self.max_level_continue_rect = pygame.Rect(card.x + 24, btn_y, btn_w, 42)
        self.max_level_menu_rect = pygame.Rect(self.max_level_continue_rect.right + 10, btn_y, btn_w, 42)
        self.ui.draw_button(self.max_level_continue_rect, "Продолжить играть", active=True)
        self.ui.draw_button(self.max_level_menu_rect, "В главное меню", active=False)

        hint = self.ui.font_tiny.render("Enter / Space / Esc - продолжить", True, self.ui.theme.text)
        self.screen.blit(hint, (card.x + 24, card.bottom - 28))

    def _dim_panel(self, rect: pygame.Rect) -> None:
        overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        overlay.fill((10, 12, 20, 160))
        self.screen.blit(overlay, (rect.x, rect.y))

    def _render_panel_feedback(self, rect: pygame.Rect, slot_index: int) -> None:
        now_ms = pygame.time.get_ticks()
        if now_ms - self.last_feedback_ms > 450:
            return
        if self.last_feedback_slot_index != slot_index:
            return
        color = self.ui.theme.accent if self.last_feedback_ok else self.ui.theme.alert
        overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        overlay.fill((*color, 55))
        self.screen.blit(overlay, (rect.x, rect.y))

    def _render_start_screen(self) -> None:
        self.auth_card_rect = None
        self.auth_username_rect = None
        self.auth_password_rect = None
        self.auth_submit_rect = None
        self.auth_toggle_rect = None
        self.start_button_rect = None
        self.resume_button_rect = None
        self.restart_button_rect = None
        self.menu_button_rect = None
        self.exit_button_rect = None
        self.mode_toggle_rect = None
        self.level_transition_toggle_rect = None
        self.instructions_button_rect = None
        self.logout_button_rect = None
        self.telemetry_url_rect = None
        self.telemetry_save_rect = None
        self.telemetry_check_rect = None
        self.instructions_start_rect = None
        self.instructions_close_rect = None
        self.max_level_continue_rect = None
        self.max_level_menu_rect = None

        full = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        full.fill((6, 8, 14, 220))
        self.screen.blit(full, (0, 0))

        title_shadow = self.ui.font_big.render("Deep Space Ops", True, (12, 20, 40))
        title_main = self.ui.font_big.render("Deep Space Ops", True, self.ui.theme.accent)
        title_rect = title_main.get_rect(center=(self.ui.w // 2, 48))
        self.screen.blit(title_shadow, (title_rect.x + 2, title_rect.y + 2))
        self.screen.blit(title_main, title_rect)

        if not self.authenticated:
            phrase = "Проходи задания и облетай планеты одну за другой."
            phrase_surf = self.ui.font_mid.render(phrase, True, self.ui.theme.text)
            phrase_rect = phrase_surf.get_rect(center=(self.ui.w // 2, 220))
            self.screen.blit(phrase_surf, phrase_rect)

            auth_w = min(620, self.ui.w - 80)
            auth_h = 320
            self.auth_card_rect = pygame.Rect(0, 0, auth_w, auth_h)
            self.auth_card_rect.center = (self.ui.w // 2, self.ui.h // 2 + 70)
            pygame.draw.rect(self.screen, (20, 28, 44), self.auth_card_rect, border_radius=14)
            pygame.draw.rect(self.screen, self.ui.theme.accent, self.auth_card_rect, width=2, border_radius=14)
            self._render_auth_panel(self.auth_card_rect)
            return

        margin = 20
        col_gap = 20
        row_gap = 12
        main_top = 84
        main_bottom = self.ui.h - 24
        main_height = max(240, main_bottom - main_top)

        left_w = self.ui.left_panel.width
        right_w = self.ui.right_panel.width
        center_w = self.ui.w - margin * 2 - col_gap * 2 - left_w - right_w
        top_row_h = int(main_height * 0.38)
        top_row_h = max(220, min(top_row_h, 300))
        profile_h = max(180, main_height - top_row_h - row_gap)

        left_box = pygame.Rect(margin, main_top, left_w, top_row_h)
        center_box = pygame.Rect(left_box.right + col_gap, main_top, center_w, top_row_h)
        right_top_box = pygame.Rect(center_box.right + col_gap, main_top, right_w, top_row_h)
        profile_box = pygame.Rect(margin, main_top + top_row_h + row_gap, self.ui.w - margin * 2, profile_h)

        for rect in [center_box, left_box, right_top_box, profile_box]:
            pygame.draw.rect(self.screen, self.ui.theme.panel, rect, border_radius=12)
            pygame.draw.rect(self.screen, self.ui.theme.border, rect, width=2, border_radius=12)

        intro_lines = [
            "Ты - оператор космической станции.",
            "Поддерживай стабильность и отвечай точно.",
            "Проходи задания и облетай планеты.",
        ]
        yy = center_box.y + 48
        for line in intro_lines:
            surf = self.ui.font_small.render(line, True, self.ui.theme.text)
            self.screen.blit(surf, (center_box.x + 20, yy))
            yy += 24

        controls_y = max(yy + 8, center_box.bottom - 96)
        action_gap = 10
        action_w = (center_box.width - 20 * 2 - action_gap) // 2
        right_x = center_box.x + 20 + action_w + action_gap
        bottom_row_y = controls_y + 44

        if self.awaiting_run_setup:
            if self._has_saved_run_for_user():
                self.resume_button_rect = pygame.Rect(center_box.x + 20, controls_y, action_w, 36)
                self.ui.draw_button(self.resume_button_rect, "Продолжить сессию", active=True)
                self.restart_button_rect = pygame.Rect(right_x, controls_y, action_w, 36)
                self.ui.draw_button(self.restart_button_rect, "Начать с 1 уровня", active=False)
            else:
                has_history = self.user_progress.get("sessions", 0) > 0
                if has_history:
                    level = int(self.user_progress.get("last_level", 1))
                    self.resume_button_rect = pygame.Rect(center_box.x + 20, controls_y, action_w, 36)
                    self.ui.draw_button(self.resume_button_rect, f"Продолжить с ур. {level}", active=True)
                    self.restart_button_rect = pygame.Rect(right_x, controls_y, action_w, 36)
                    self.ui.draw_button(self.restart_button_rect, "Начать с 1 уровня", active=False)
                else:
                    self.start_button_rect = pygame.Rect(center_box.x + 20, controls_y, action_w, 36)
                    self.ui.draw_button(self.start_button_rect, "Старт", active=True)
                    self.restart_button_rect = pygame.Rect(right_x, controls_y, action_w, 36)
                    self.ui.draw_button(self.restart_button_rect, "Начать с 1 уровня", active=False)
        else:
            self.resume_button_rect = pygame.Rect(center_box.x + 20, controls_y, action_w, 36)
            self.ui.draw_button(self.resume_button_rect, "Продолжить сессию", active=True)
            self.restart_button_rect = pygame.Rect(right_x, controls_y, action_w, 36)
            self.ui.draw_button(self.restart_button_rect, "Начать с 1 уровня", active=False)
        self.logout_button_rect = pygame.Rect(center_box.x + 20, bottom_row_y, action_w, 36)
        self.ui.draw_button(self.logout_button_rect, "Сменить пользователя", active=False)
        self.exit_button_rect = pygame.Rect(right_x, bottom_row_y, action_w, 36)
        self.ui.draw_button(self.exit_button_rect, "Выход из приложения", active=False)

        mode_title = self.ui.font_small.render("Текущий режим адаптации:", True, self.ui.theme.accent)
        self.screen.blit(mode_title, (right_top_box.x + 16, right_top_box.y + 16))
        mode_label = "Базовый" if self.selected_mode == "baseline" else "Адаптивный"
        mode_value = self.ui.font_mid.render(mode_label, True, self.ui.theme.text)
        self.screen.blit(mode_value, (right_top_box.x + 16, right_top_box.y + 46))
        self.mode_toggle_rect = pygame.Rect(right_top_box.x + 16, right_top_box.y + 96, right_top_box.width - 32, 28)
        self._draw_compact_button(self.mode_toggle_rect, "Сменить режим", active=False)
        transition_label = "Переход: Пауза" if self.pause_between_levels else "Переход: Авто"
        transition_state = self.ui.font_small.render(transition_label, True, self.ui.theme.text)
        self.screen.blit(transition_state, (right_top_box.x + 16, right_top_box.y + 134))
        self.level_transition_toggle_rect = pygame.Rect(right_top_box.x + 16, right_top_box.y + 170, right_top_box.width - 32, 28)
        self._draw_compact_button(self.level_transition_toggle_rect, "Переключить переход", active=False)
        self.instructions_button_rect = pygame.Rect(
            right_top_box.x + 16,
            right_top_box.bottom - 44,
            right_top_box.width - 32,
            28,
        )
        self._draw_compact_button(self.instructions_button_rect, "Инструкция", active=False)

        warning = self._rl_warning()
        if warning:
            warning_y = self.instructions_button_rect.y - self.ui.font_tiny.get_height() - 8
            warning_surf = self.ui.font_tiny.render(warning, True, self.ui.theme.alert)
            self.screen.blit(warning_surf, (right_top_box.x + 16, warning_y))

        profile_title = self.ui.font_small.render("Профиль", True, self.ui.theme.accent)
        self.screen.blit(profile_title, (profile_box.x + 16, profile_box.y + 16))
        self._render_user_progress(profile_box)
        self._render_profile_graph(profile_box)
        self._render_profile_motivation(profile_box)
        tasks_title = self.ui.font_small.render("Задачи", True, self.ui.theme.accent)
        self.screen.blit(tasks_title, (left_box.x + 16, left_box.y + 16))
        task_lines = [
            "1. Сравнение кодов",
            "2. Память последовательностей",
            "3. Переключение правил",
            "4. Четность числа",
            "5. Радарный сигнал",
        ]
        yy = left_box.y + 50
        for line in task_lines:
            yy = self._draw_wrapped_text(
                line,
                left_box.x + 16,
                yy,
                left_box.width - 28,
                self.ui.font_tiny,
                self.ui.theme.text,
                line_h=21,
            )

    def _render_instructions_overlay(self) -> None:
        self.instructions_start_rect = None
        self.instructions_close_rect = None

        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((4, 6, 12, 235))
        self.screen.blit(overlay, (0, 0))

        card_w = min(960, self.ui.w - 80)
        card_h = min(700, self.ui.h - 80)
        card = pygame.Rect(0, 0, card_w, card_h)
        card.center = (self.ui.w // 2, self.ui.h // 2)
        pygame.draw.rect(self.screen, (17, 24, 40), card, border_radius=16)
        pygame.draw.rect(self.screen, self.ui.theme.accent, card, width=2, border_radius=16)

        title = self.ui.font_big.render("Как играть", True, self.ui.theme.accent)
        self.screen.blit(title, (card.x + 24, card.y + 20))

        subtitle = "Сначала посмотри, что значит каждая кнопка. Потом нажми Начать."
        subtitle_y = self._draw_wrapped_text(
            subtitle,
            card.x + 24,
            card.y + 70,
            card.width - 48,
            self.ui.font_small,
            self.ui.theme.text,
            line_h=self.ui.font_small.get_height() + 4,
        )

        step_gap = 18
        section_gap = 10
        left_col_x = card.x + 24
        col_w = (card.width - 72) // 2
        right_col_x = left_col_x + col_w + 24
        content_top = subtitle_y + 10

        left_box = pygame.Rect(left_col_x, content_top, col_w, card.height - 190)
        right_box = pygame.Rect(right_col_x, content_top, col_w, card.height - 190)
        for rect in (left_box, right_box):
            pygame.draw.rect(self.screen, (12, 17, 30), rect, border_radius=12)
            pygame.draw.rect(self.screen, self.ui.theme.border, rect, width=1, border_radius=12)

        header_1 = self.ui.font_mid.render("Шаги", True, self.ui.theme.accent)
        self.screen.blit(header_1, (left_box.x + 16, left_box.y + 14))
        steps = [
            "1. Посмотри на задание в активной панели справа.",
            "2. Реши, верно ли утверждение или есть ли цель в сигнале.",
            "3. Нажми F для ответа ДА.",
            "4. Нажми J для ответа НЕТ.",
            "5. Действуй быстро: таймер идет, а между этапами будет пауза.",
        ]
        yy = left_box.y + 52
        for step in steps:
            yy = self._draw_wrapped_text(
                step,
                left_box.x + 16,
                yy,
                left_box.width - 32,
                self.ui.font_small,
                self.ui.theme.text,
                line_h=self.ui.font_small.get_height() + 4,
            )
            yy += section_gap

        header_2 = self.ui.font_mid.render("Куда нажимать", True, self.ui.theme.accent)
        self.screen.blit(header_2, (right_box.x + 16, right_box.y + 14))
        self._draw_direction_arrow(
            start=(right_box.x + 42, right_box.y + 96),
            end=(right_box.centerx - 40, right_box.y + 96),
            color=self.ui.theme.accent,
            points_left=True,
        )
        self._draw_direction_arrow(
            start=(right_box.centerx + 40, right_box.y + 96),
            end=(right_box.right - 42, right_box.y + 96),
            color=self.ui.theme.alert,
            points_left=False,
        )
        left_key = self.ui.font_huge.render("F", True, self.ui.theme.accent)
        right_key = self.ui.font_huge.render("J", True, self.ui.theme.alert)
        self.screen.blit(left_key, left_key.get_rect(center=(right_box.x + 86, right_box.y + 148)))
        self.screen.blit(right_key, right_key.get_rect(center=(right_box.right - 86, right_box.y + 148)))

        mappings = [
            "F - Да: совпадает, есть метка, верно.",
            "J - Нет: не совпадает, метки нет, неверно.",
            "Esc - Пауза во время сессии.",
            "Смотри на активную карточку: остальные панели только фон.",
        ]
        yy = right_box.y + 220
        for line in mappings:
            yy = self._draw_wrapped_text(
                line,
                right_box.x + 16,
                yy,
                right_box.width - 32,
                self.ui.font_small,
                self.ui.theme.text,
                line_h=self.ui.font_small.get_height() + 4,
            )
            yy += section_gap

        footer_y = card.bottom - 72
        button_w = max(220, min(320, (card.width - 72) // 2))
        self.instructions_start_rect = pygame.Rect(card.x + 24, footer_y, button_w, 42)
        self.instructions_close_rect = pygame.Rect(card.right - 24 - button_w, footer_y, button_w, 42)
        self.ui.draw_button(self.instructions_start_rect, "Понятно, начать", active=True)
        self.ui.draw_button(self.instructions_close_rect, "Закрыть и вернуться", active=False)

        hint = self.ui.font_tiny.render("Enter или Space - начать, Esc - закрыть", True, self.ui.theme.text)
        self.screen.blit(hint, (card.x + 24, card.bottom - 28))

    def _render_telemetry_panel(self, top_y: int, preferred_h: int) -> None:
        safe_top = min(top_y, self.ui.h - 100)
        panel_h = max(88, min(preferred_h, self.ui.h - safe_top - 12))
        panel = pygame.Rect(20, safe_top, self.ui.w - 40, panel_h)
        pygame.draw.rect(self.screen, (15, 20, 34), panel, border_radius=10)
        pygame.draw.rect(self.screen, self.ui.theme.border, panel, width=2, border_radius=10)

        status_text, ok = self._telemetry_status_text()
        status_color = self.ui.theme.accent if ok else self.ui.theme.alert
        words = status_text.split()
        lines: List[str] = []
        current = ""
        max_width = panel.width - 28
        for word in words:
            candidate = f"{current} {word}".strip()
            if self.ui.font_tiny.size(candidate)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if not lines:
            lines = [status_text]

        title_h = self.ui.font_tiny.get_height()
        row_h = 30
        line_h = 18
        status_h = max(line_h, len(lines) * line_h)
        content_h = title_h + 8 + row_h + 10 + status_h
        start_y = panel.y + max(8, (panel.height - content_h) // 2)

        title = self.ui.font_tiny.render("Телеметрия: адрес отправки данных", True, self.ui.theme.accent)
        self.screen.blit(title, (panel.x + 14, start_y))

        check_w = max(90, self.ui.font_tiny.size("Проверить")[0] + 26)
        save_w = max(82, self.ui.font_tiny.size("Сохранить")[0] + 24)
        buttons_w = check_w + save_w + 18
        row_y = start_y + title_h + 8
        url_w = max(180, panel.width - buttons_w - 38)
        self.telemetry_url_rect = pygame.Rect(panel.x + 14, row_y, url_w, row_h)
        pygame.draw.rect(self.screen, (9, 12, 22), self.telemetry_url_rect, border_radius=8)
        border = self.ui.theme.accent if self.telemetry_input_focused else self.ui.theme.border
        pygame.draw.rect(self.screen, border, self.telemetry_url_rect, width=2, border_radius=8)
        url_text = self.telemetry_url_value or "https://..."
        url_color = self.ui.theme.text if self.telemetry_url_value else (140, 150, 175)
        visible_url = url_text
        max_url_w = self.telemetry_url_rect.width - 16
        while self.ui.font_tiny.size(visible_url)[0] > max_url_w and len(visible_url) > 4:
            visible_url = "..." + visible_url[4:]
        url_surface = self.ui.font_tiny.render(visible_url, True, url_color)
        self.screen.blit(url_surface, (self.telemetry_url_rect.x + 8, self.telemetry_url_rect.y + 5))

        self.telemetry_check_rect = pygame.Rect(self.telemetry_url_rect.right + 10, row_y + 1, check_w, 28)
        self._draw_compact_button(self.telemetry_check_rect, "Проверить", active=False)
        self.telemetry_save_rect = pygame.Rect(self.telemetry_check_rect.right + 8, row_y + 1, save_w, 28)
        self._draw_compact_button(self.telemetry_save_rect, "Сохранить", active=True)

        line_y = row_y + row_h + 10
        for line in lines:
            surf = self.ui.font_tiny.render(line, True, status_color)
            line_rect = surf.get_rect(center=(panel.centerx, line_y + surf.get_height() // 2))
            self.screen.blit(surf, line_rect)
            line_y += line_h

    def _render_auth_panel(self, rect: pygame.Rect) -> None:
        x = rect.x + 20
        y = rect.y + 18
        mode_label = "Вход" if self.auth_mode == "login" else "Регистрация"
        title = self.ui.font_mid.render(f"Аккаунт: {mode_label}", True, self.ui.theme.accent)
        self.screen.blit(title, (x, y))

        self.auth_username_rect = pygame.Rect(x, y + 38, rect.width - 40, 42)
        self.auth_password_rect = pygame.Rect(x, y + 88, rect.width - 40, 42)
        for field_rect, active in (
            (self.auth_username_rect, self.auth_focus == "username"),
            (self.auth_password_rect, self.auth_focus == "password"),
        ):
            pygame.draw.rect(self.screen, (13, 17, 30), field_rect, border_radius=10)
            pygame.draw.rect(self.screen, self.ui.theme.accent if active else self.ui.theme.border, field_rect, width=2, border_radius=10)

        username_line = self.ui.font_small.render(f"Логин: {self.auth_username or ''}", True, self.ui.theme.text)
        masked = "*" * len(self.auth_password) if self.auth_password else "_"
        password_line = self.ui.font_small.render(f"Пароль: {masked}", True, self.ui.theme.text)
        self.screen.blit(username_line, (self.auth_username_rect.x + 12, self.auth_username_rect.y + 9))
        self.screen.blit(password_line, (self.auth_password_rect.x + 12, self.auth_password_rect.y + 9))

        self.auth_submit_rect = pygame.Rect(x, y + 142, rect.width - 40, 44)
        self.auth_toggle_rect = pygame.Rect(x, y + 192, rect.width - 40, 34)
        self.ui.draw_button(self.auth_submit_rect, "Подтвердить", active=True)
        toggle_label = "Переключить: вход/регистрация"
        self.ui.draw_button(self.auth_toggle_rect, toggle_label, active=False)

        if self.auth_message:
            msg_surface = self.ui.font_small.render(self.auth_message, True, self.ui.theme.text)
            self.screen.blit(msg_surface, (x, rect.bottom - 34))

    def _render_user_progress(self, rect: pygame.Rect) -> None:
        x = rect.x + 16
        y = rect.y + 56
        live = self._current_session_stats()
        saved_sessions = int(self.user_progress["sessions"])
        saved_avg_acc = float(self.user_progress["avg_accuracy"])
        saved_avg_rt = float(self.user_progress["avg_rt"])

        # Показываем "общую" статистику с учетом текущей сессии, чтобы цифры были актуальны сразу.
        if live is not None and live["tasks"] > 0:
            combined_total_sessions = saved_sessions + 1
            combined_avg_acc = ((saved_avg_acc * saved_sessions) + live["accuracy"]) / max(1, combined_total_sessions)
            combined_avg_rt = ((saved_avg_rt * saved_sessions) + live["mean_rt"]) / max(1, combined_total_sessions)
        else:
            combined_avg_acc = saved_avg_acc
            combined_avg_rt = saved_avg_rt

        lines = [
            f"Пилот: {self.user_id}",
            f"Планет всего: {int(self._total_planets_overall())}",
            f"Средняя точность: {int(combined_avg_acc * 100)}%",
            f"Среднее время ответа: {int(combined_avg_rt)} мс",
        ]
        yy = y
        for line in lines:
            surf = self.ui.font_small.render(line, True, self.ui.theme.text)
            self.screen.blit(surf, (x, yy))
            yy += 24

    def _render_profile_graph(self, rect: pygame.Rect) -> None:
        stats_w = 420
        gap = 14
        graph_w = 360
        graph_x = rect.x + 16 + stats_w + gap
        graph_rect = pygame.Rect(graph_x, rect.y + 52, graph_w, rect.height - 88)
        pygame.draw.rect(self.screen, (14, 18, 32), graph_rect, border_radius=10)
        pygame.draw.rect(self.screen, self.ui.theme.border, graph_rect, width=1, border_radius=10)
        title = self.ui.font_tiny.render("Точность по последним сессиям", True, self.ui.theme.text)
        self.screen.blit(title, (graph_rect.x + 10, graph_rect.y + 8))

        sessions = list(self.user_recent_sessions[-8:])
        run_points = self._current_run_accuracy_points()
        if run_points:
            sessions.extend({"accuracy_total": p} for p in run_points[-3:])
        live = self._current_session_stats()
        if live is not None and live["tasks"] > 0 and not run_points:
            sessions.append({"accuracy_total": live["accuracy"]})
        if not sessions:
            empty = self.ui.font_tiny.render("Пока нет данных", True, self.ui.theme.text)
            self.screen.blit(empty, (graph_rect.x + 10, graph_rect.centery))
            return

        values = [max(0.0, min(1.0, float(s.get("accuracy_total", 0.0)))) for s in sessions]
        plot = pygame.Rect(graph_rect.x + 12, graph_rect.y + 32, graph_rect.width - 24, graph_rect.height - 46)
        pygame.draw.rect(self.screen, (10, 13, 24), plot, border_radius=8)

        if len(values) == 1:
            cx = plot.x + plot.width // 2
            cy = plot.bottom - int(values[0] * (plot.height - 8)) - 4
            pygame.draw.circle(self.screen, self.ui.theme.accent, (cx, cy), 4)
            return

        step = plot.width / (len(values) - 1)
        points = []
        for i, value in enumerate(values):
            px = int(plot.x + i * step)
            py = int(plot.bottom - value * (plot.height - 8) - 4)
            points.append((px, py))
        if len(points) >= 2:
            pygame.draw.lines(self.screen, self.ui.theme.accent, False, points, 2)
        for p in points:
            pygame.draw.circle(self.screen, self.ui.theme.accent, p, 3)

    def _current_run_accuracy_points(self) -> List[float]:
        if not self.results:
            return []
        batch_size = max(1, int(self.session.total_tasks))
        points: List[float] = []
        for start in range(0, len(self.results), batch_size):
            chunk = self.results[start : start + batch_size]
            if not chunk:
                continue
            acc = sum(1 for r in chunk if r.correct) / len(chunk)
            points.append(max(0.0, min(1.0, acc)))
        return points

    def _render_profile_motivation(self, rect: pygame.Rect) -> None:
        phrase = self.current_motivation_phrase
        stats_w = 420
        gap = 14
        graph_w = 360
        box_x = rect.x + 16 + stats_w + gap + graph_w + gap
        box_w = rect.right - 16 - box_x
        box = pygame.Rect(box_x, rect.y + 52, max(180, box_w), rect.height - 88)
        pygame.draw.rect(self.screen, (14, 18, 32), box, border_radius=10)
        pygame.draw.rect(self.screen, self.ui.theme.border, box, width=1, border_radius=10)
        self._draw_fitted_quote(
            text=phrase,
            rect=pygame.Rect(box.x + 10, box.y + 12, box.width - 20, box.height - 24),
            color=self.ui.theme.accent,
        )

    def _draw_fitted_quote(
        self,
        text: str,
        rect: pygame.Rect,
        color: tuple[int, int, int],
    ) -> None:
        if not text.strip():
            return

        max_size = max(18, int(self.ui.font_small.get_height() * 1.15))
        min_size = max(12, int(self.ui.font_tiny.get_height() * 0.95))

        for size in range(max_size, min_size - 1, -1):
            font = self.ui._make_font(size, bold=True)
            line_h = font.get_height() + 4
            lines = self._wrap_text_for_font(text, font, rect.width)
            total_h = len(lines) * line_h
            if total_h <= rect.height:
                yy = rect.y + max(0, (rect.height - total_h) // 2)
                for line in lines:
                    surf = font.render(line, True, color)
                    self.screen.blit(surf, (rect.x, yy))
                    yy += line_h
                return

        fallback = self.ui._make_font(min_size, bold=True)
        lines = self._wrap_text_for_font(text, fallback, rect.width)
        line_h = fallback.get_height() + 2
        max_lines = max(1, rect.height // line_h)
        clipped = lines[:max_lines]
        if clipped and len(lines) > max_lines:
            last = clipped[-1]
            while len(last) > 3 and fallback.size(last + "...")[0] > rect.width:
                last = last[:-1]
            clipped[-1] = last + "..."
        yy = rect.y
        for line in clipped:
            surf = fallback.render(line, True, color)
            self.screen.blit(surf, (rect.x, yy))
            yy += line_h

    @staticmethod
    def _wrap_text_for_font(text: str, font: pygame.font.Font, max_width: int) -> List[str]:
        words = text.split()
        if not words:
            return [""]
        lines: List[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if not current or font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    def _roll_motivation_phrase(self) -> None:
        if not self.motivation_phrases:
            self.current_motivation_phrase = ""
            return
        if len(self.motivation_phrases) == 1:
            self.current_motivation_phrase = self.motivation_phrases[0]
            return
        prev = self.current_motivation_phrase
        candidates = [p for p in self.motivation_phrases if p != prev]
        self.current_motivation_phrase = self.slot_rng.choice(candidates)

    def _draw_compact_button(self, rect: pygame.Rect, label: str, active: bool = False) -> None:
        fill = (24, 32, 50) if not active else (20, 46, 58)
        border = self.ui.theme.accent if active else self.ui.theme.border
        pygame.draw.rect(self.screen, fill, rect, border_radius=8)
        pygame.draw.rect(self.screen, border, rect, width=2, border_radius=8)
        font = self.ui.font_tiny
        if font.size(label)[0] > rect.width - 10:
            fallback = self.ui._make_font(max(12, int(self.ui.font_tiny.get_height() * 0.85)))
            clipped = label
            while len(clipped) > 3 and fallback.size(clipped + "...")[0] > rect.width - 10:
                clipped = clipped[:-1]
            text = fallback.render((clipped + "...") if clipped != label else label, True, self.ui.theme.text)
        else:
            text = font.render(label, True, self.ui.theme.text)
        text_rect = text.get_rect(center=rect.center)
        self.screen.blit(text, text_rect)

    def _draw_direction_arrow(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        color: tuple[int, int, int],
        points_left: bool,
    ) -> None:
        pygame.draw.line(self.screen, color, start, end, 4)
        head = 12
        tip = start if points_left else end
        if points_left:
            points = [
                tip,
                (tip[0] + head, tip[1] - head // 2),
                (tip[0] + head, tip[1] + head // 2),
            ]
        else:
            points = [
                tip,
                (tip[0] - head, tip[1] - head // 2),
                (tip[0] - head, tip[1] + head // 2),
            ]
        pygame.draw.polygon(self.screen, color, points)

    def _handle_runtime_error(self, stage: str, exc: Exception) -> None:
        self.last_feedback_text = "Ошибка рендера. Проверь лог client_errors.log"
        self.last_feedback_ok = False
        self.last_feedback_ms = pygame.time.get_ticks()
        self.last_feedback_duration_ms = 4000
        self.started = False
        self.pause_menu_open = False
        payload = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        try:
            with self.error_log_path.open("a", encoding="utf-8") as f:
                f.write(f"\n[{int(time.time())}] stage={stage}\n{payload}\n")
        except OSError:
            pass

    def _handle_auth_event(self, event: pygame.event.Event) -> None:
        handle_auth_event(self, event)

    def _handle_auth_mouse(self, pos: tuple[int, int]) -> None:
        handle_auth_mouse(self, pos)

    def _handle_menu_mouse(self, pos: tuple[int, int]) -> None:
        handle_menu_mouse(self, pos)

    def _handle_pause_menu_mouse(self, pos: tuple[int, int]) -> None:
        handle_pause_menu_mouse(self, pos)

    def _handle_instructions_mouse(self, pos: tuple[int, int]) -> None:
        if self.instructions_start_rect and self.instructions_start_rect.collidepoint(pos):
            self._complete_instructions()
            return
        if self.instructions_close_rect and self.instructions_close_rect.collidepoint(pos):
            self._close_instructions()
            return

    def _handle_max_level_popup_mouse(self, pos: tuple[int, int]) -> None:
        if self.max_level_continue_rect and self.max_level_continue_rect.collidepoint(pos):
            self._continue_after_max_level_popup()
            return
        if self.max_level_menu_rect and self.max_level_menu_rect.collidepoint(pos):
            self._return_to_menu_after_max_level_popup()
            return

    def _submit_auth(self) -> None:
        username = self.auth_username.strip()
        password = self.auth_password
        if not username or not password:
            self.auth_message = "Заполни логин и пароль"
            return
        if self.auth_mode == "register":
            ok, msg, user_id = self.auth_store.register(username, password)
        else:
            ok, msg, user_id = self.auth_store.authenticate(username, password)
        self.auth_message = msg
        if not ok:
            return

        self.user_id = user_id
        self.authenticated = True
        self.auth_password = ""
        self.user_progress = self._load_user_progress(self.user_id)
        self.user_recent_sessions = self._load_recent_sessions(self.user_id)
        self.saved_run_preview_stats = self._load_saved_run_preview_stats()
        self.awaiting_run_setup = True
        self.pause_menu_open = False
        if self._has_saved_run_for_user():
            self.auth_message = "Найдена незавершенная сессия. Можно продолжить."
        self._roll_motivation_phrase()

    def _load_telemetry_settings(self) -> tuple[str, str]:
        env_url = os.getenv("NEUROGAME_TELEMETRY_URL", "").strip()
        env_key = os.getenv("NEUROGAME_TELEMETRY_API_KEY", "").strip()
        if not env_key:
            env_key = os.getenv("NEUROGAME_API_KEY", "").strip()
        return load_telemetry_settings_file(
            settings_path=self.telemetry_settings_path,
            default_url=self.default_telemetry_url,
            default_key=env_key,
            env_url=env_url,
            env_key=env_key,
        )

    def _save_telemetry_settings(self, endpoint_url: str, api_key: str) -> None:
        save_telemetry_settings_file(
            settings_path=self.telemetry_settings_path,
            endpoint_url=endpoint_url,
            api_key=api_key,
        )

    def _telemetry_status_text(self) -> tuple[str, bool]:
        url = self.telemetry_url_value.strip()
        if not url:
            return "Адрес не указан. Свяжитесь с тех. специалистом.", False
        if not TelemetryClient.is_valid_endpoint(url):
            return "Некорректный адрес. Укажите http(s)-адрес сервера.", False
        if self.telemetry.last_error == "invalid_api_key":
            return "Неверный API-ключ телеметрии. Проверьте NEUROGAME_API_KEY.", False
        if self.telemetry.last_error.startswith("http_"):
            return "Сервер телеметрии ответил ошибкой. Проверьте доступ и настройки.", False
        if self.telemetry_status_message:
            return self.telemetry_status_message, self.telemetry_status_ok
        if self.telemetry.queue_size() > 0:
            return f"Нет связи: в очереди {self.telemetry.queue_size()} событий, отправим позже.", False
        return "Адрес настроен. Нажмите Проверить для проверки связи.", True

    def _save_telemetry_url(self) -> None:
        url = self.telemetry_url_value.strip()
        if not TelemetryClient.is_valid_endpoint(url):
            self.telemetry_status_message = "Некорректный адрес. Укажите http(s)-адрес."
            self.telemetry_status_ok = False
            return
        self.telemetry.set_endpoint(url)
        self.auth_store.set_backend(url, self.telemetry_api_key_value)
        self._save_telemetry_settings(url, self.telemetry_api_key_value)
        self.telemetry_status_message = "Адрес сохранен."
        self.telemetry_status_ok = True

    def _check_telemetry_connection(self) -> None:
        self.telemetry.set_endpoint(self.telemetry_url_value.strip())
        self.auth_store.set_backend(self.telemetry_url_value.strip(), self.telemetry_api_key_value)
        ok, message = self.telemetry.check_connection()
        self.telemetry_status_message = message
        self.telemetry_status_ok = ok

    def _handle_telemetry_event(self, event: pygame.event.Event) -> bool:
        return handle_telemetry_event(self, event)

    def _pause_run(self, open_pause_menu: bool = True) -> None:
        if not self._has_resumable_run():
            return
        self.started = False
        self.pause_menu_open = open_pause_menu
        self.telemetry.track(
            event_type="session_pause",
            user_id=self.user_id,
            session_id=self.session_id,
            model_version=self._model_version(),
            payload={
                "session_id": self.session_id,
                "user_id": self.user_id,
                "mode": self._effective_mode(),
                "reason": "pause_menu" if open_pause_menu else "menu",
            },
        )
        self._save_active_run_snapshot()

    def _exit_app(self) -> None:
        if self._has_resumable_run():
            self._emit_partial_session_end(reason="menu_exit")
            self._save_active_run_snapshot()
            self.persist_active_run_on_exit = True
        self.running = False

    def _emit_partial_session_end(self, reason: str) -> None:
        if self.partial_session_end_emitted:
            return
        if not self.user_id or not self.session_id:
            return
        tasks = len(self.results)
        if tasks > 0:
            accuracy = sum(1 for r in self.results if r.correct) / tasks
            rts = [r.rt_ms for r in self.results if r.rt_ms is not None]
            mean_rt = statistics.mean(rts) if rts else 0.0
            rt_variance = statistics.pvariance(rts) if len(rts) > 1 else 0.0
        else:
            accuracy = 0.0
            mean_rt = 0.0
            rt_variance = 0.0
        payload = {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "total_tasks": tasks,
            "accuracy_total": accuracy,
            "mean_rt": mean_rt,
            "rt_variance": rt_variance,
            "switch_cost": 0.0,
            "fatigue_trend": 0.0,
            "overload_events": 0,
            "max_level": self.current_level,
            "last_level": self.current_level,
            "planets_visited": self.planets_visited,
            "mode": self._effective_mode(),
            "is_partial": 1,
            "exit_reason": reason,
            "task_offsets": dict(self.task_offsets),
        }
        self.telemetry.track(
            event_type="session_end_partial",
            user_id=self.user_id,
            session_id=self.session_id,
            model_version=self._model_version(),
            payload=payload,
        )
        self.partial_session_end_emitted = True

    def _has_resumable_run(self) -> bool:
        return self.authenticated and (self.started or not self.awaiting_run_setup)

    def _load_pending_runs(self) -> dict:
        return load_pending_runs_file(self.pending_runs_path)

    def _save_pending_runs(self, runs: dict) -> None:
        save_pending_runs_file(self.pending_runs_path, runs)

    def _has_saved_run_for_user(self) -> bool:
        if not self.user_id:
            return False
        runs = self._load_pending_runs()
        return self.user_id in runs

    def _save_active_run_snapshot(self) -> None:
        if not self._has_resumable_run() or not self.user_id:
            return
        answered_in_batch = max(0, len(self.results) - self.batch_result_start)
        snapshot = {
            "session_id": self.session_id,
            "current_level": self.current_level,
            "tempo_offset": self.tempo_offset,
            "task_offsets": dict(self.task_offsets),
            "selected_mode": self.selected_mode,
            "stability": self.stability,
            "batch_result_start": self.batch_result_start,
            "batch_index": self.batch_index,
            "planets_visited": self.planets_visited,
            "pause_between_levels": self.pause_between_levels,
            "awaiting_run_setup": self.awaiting_run_setup,
            "last_feedback_text": self.last_feedback_text,
            "last_feedback_ok": self.last_feedback_ok,
            "adapt_step": self.adapt_step,
            "last_adapt_state": self.last_adapt_state,
            "last_adapt_action": self.last_adapt_action,
            "last_adapt_reward": self.last_adapt_reward,
            "results": [r.__dict__ for r in self.results],
            "batch_tasks_done": answered_in_batch,
        }
        runs = self._load_pending_runs()
        runs[self.user_id] = snapshot
        self._save_pending_runs(runs)
        self.saved_run_preview_stats = self._summarize_task_results(self.results)

    def _clear_saved_run(self) -> None:
        if not self.user_id:
            return
        runs = self._load_pending_runs()
        if self.user_id not in runs:
            return
        runs.pop(self.user_id, None)
        self._save_pending_runs(runs)
        self.saved_run_preview_stats = None

    def _restore_saved_run(self) -> bool:
        if not self.user_id:
            return False
        runs = self._load_pending_runs()
        snapshot = runs.get(self.user_id)
        if not isinstance(snapshot, dict):
            return False

        self.session_id = str(snapshot.get("session_id", f"s{int(time.time())}_{self.user_id}"))
        self.current_level = max(
            self.level_cfg.min_level,
            min(self.level_cfg.max_level, int(snapshot.get("current_level", self.level_cfg.start_level))),
        )
        self.tempo_offset = self._clamp_tempo_for_level(int(snapshot.get("tempo_offset", 0)), self.current_level)
        raw_offsets = snapshot.get("task_offsets", {})
        self.task_offsets = self._normalize_task_offsets(raw_offsets)
        self.selected_mode = str(snapshot.get("selected_mode", self.session.adaptation_mode))
        self.stability = max(0.0, min(1.0, float(snapshot.get("stability", 0.0))))
        self.batch_result_start = max(0, int(snapshot.get("batch_result_start", 0)))
        self.batch_index = max(1, int(snapshot.get("batch_index", 1)))
        self.planets_visited = max(0, int(snapshot.get("planets_visited", 0)))
        self.pause_between_levels = bool(snapshot.get("pause_between_levels", True))
        self.awaiting_run_setup = bool(snapshot.get("awaiting_run_setup", False))
        self.last_feedback_text = str(snapshot.get("last_feedback_text", ""))
        self.last_feedback_ok = bool(snapshot.get("last_feedback_ok", True))
        self.adapt_step = max(0, int(snapshot.get("adapt_step", 0)))
        self.last_adapt_state = snapshot.get("last_adapt_state")
        self.last_adapt_action = snapshot.get("last_adapt_action")
        self.last_adapt_reward = snapshot.get("last_adapt_reward")

        raw_results = snapshot.get("results", [])
        restored_results: List[TaskResult] = []
        if isinstance(raw_results, list):
            for item in raw_results:
                if not isinstance(item, dict):
                    continue
                try:
                    restored_results.append(TaskResult(**item))
                except TypeError:
                    continue
        self.results = restored_results
        self.saved_run_preview_stats = None
        self.batch_result_start = min(self.batch_result_start, len(self.results))
        answered_in_batch = max(0, int(snapshot.get("batch_tasks_done", len(self.results) - self.batch_result_start)))
        answered_in_batch = min(answered_in_batch, self.session.total_tasks)

        self.current_difficulty = self._build_effective_difficulty()
        self.task_manager = TaskManager(
            self.current_difficulty,
            total_tasks=self.session.total_tasks,
            inter_task_pause_ms=self.session.inter_task_pause_ms,
            seed=1 + int(time.time()) % 997,
        )
        self.task_manager.set_level(self.current_level)
        self.task_manager.tasks_completed = answered_in_batch
        self.task_manager.tasks_created = answered_in_batch
        self.started = False
        self.pause_menu_open = False
        self.awaiting_run_setup = False
        self.partial_session_end_emitted = False
        self.task_struggle_streak = 0
        self.task_flow_streak = 0
        self.last_task_adjustment_reason = "resume"
        self.last_feedback_text = "Сессия восстановлена. Нажми Старт."
        self.last_feedback_ok = True
        self.last_feedback_ms = pygame.time.get_ticks()
        self.last_feedback_duration_ms = 2200
        self.active_slot_index = None
        self.last_focused_token = None
        self.telemetry.track(
            event_type="session_resume",
            user_id=self.user_id,
            session_id=self.session_id,
            model_version=self._model_version(),
            payload={
                "session_id": self.session_id,
                "user_id": self.user_id,
                "mode": self._effective_mode(),
                "level": self.current_level,
                "tempo_offset": self.tempo_offset,
                "batch_index": self.batch_index,
            },
        )
        self._roll_motivation_phrase()
        return True

    def _begin_user_run(self, start_level: int) -> None:
        self.current_level = max(self.level_cfg.min_level, min(self.level_cfg.max_level, start_level))
        self.tempo_offset = 0
        self.task_offsets = self._empty_task_offsets()
        self.current_difficulty = self._build_effective_difficulty()
        self.task_manager = TaskManager(
            self.current_difficulty,
            total_tasks=self.session.total_tasks,
            inter_task_pause_ms=self.session.inter_task_pause_ms,
            seed=1 + int(time.time()) % 997,
        )
        self.task_manager.set_level(self.current_level)
        self.session_id = f"s{int(time.time())}_{self.user_id}"
        self.results = []
        self.batch_result_start = 0
        self.batch_index = 1
        self.planets_visited = 0
        self.stability = 0.0
        self.last_feedback_text = ""
        self.last_feedback_ok = True
        self.last_adapt_state = None
        self.last_adapt_action = None
        self.last_adapt_reward = None
        self.adapt_step = 0
        self.awaiting_run_setup = False
        self.pause_menu_open = False
        self.started = True
        self.partial_session_end_emitted = False
        self.saved_run_preview_stats = None
        self.task_struggle_streak = 0
        self.task_flow_streak = 0
        self.last_task_adjustment_reason = "start"
        self._clear_saved_run()
        self.telemetry.track(
            event_type="session_start",
            user_id=self.user_id,
            session_id=self.session_id,
            model_version=self._model_version(),
            payload={
                "session_id": self.session_id,
                "user_id": self.user_id,
                "mode": self._effective_mode(),
                "level": self.current_level,
                "tempo_offset": self.tempo_offset,
            },
        )
        self._roll_motivation_phrase()

    def _open_instructions(self, launch_action: str | None = None) -> None:
        self.instructions_open = True
        self.instructions_launch_action = launch_action
        self.started = False
        self.pause_menu_open = False

    def _close_instructions(self) -> None:
        self.instructions_open = False
        self.instructions_launch_action = None

    def _complete_instructions(self) -> None:
        launch_action = self.instructions_launch_action
        self.instructions_completed = True
        self.instructions_open = False
        self.instructions_launch_action = None
        if launch_action == "start_new":
            self._begin_user_run(1)
        elif launch_action == "resume_saved":
            if not self._restore_saved_run():
                level = int(self.user_progress.get("last_level", 1))
                self._begin_user_run(max(1, level))
        elif launch_action == "resume_level":
            level = int(self.user_progress.get("last_level", 1))
            self._begin_user_run(max(1, level))
        elif launch_action == "continue_active":
            self.started = True

    def _open_max_level_popup(self) -> None:
        self.max_level_popup_open = True
        self.started = False
        self.pause_menu_open = False

    def _continue_after_max_level_popup(self) -> None:
        self.max_level_popup_open = False
        self.started = True
        self.pause_menu_open = False

    def _return_to_menu_after_max_level_popup(self) -> None:
        self.max_level_popup_open = False
        self.started = False
        self.pause_menu_open = False
        self._save_active_run_snapshot()

    def _logout_user(self) -> None:
        if self._has_resumable_run():
            self._emit_partial_session_end(reason="logout")
            self._save_active_run_snapshot()
        self.authenticated = False
        self.started = False
        self.pause_menu_open = False
        self.user_id = None
        self.auth_password = ""
        self.auth_message = ""
        self.user_progress = self._empty_progress()
        self.user_recent_sessions = []
        self.saved_run_preview_stats = None
        self.awaiting_run_setup = True
        self._roll_motivation_phrase()

    @staticmethod
    def _empty_progress() -> Dict[str, float]:
        return {
            "sessions": 0.0,
            "avg_accuracy": 0.0,
            "best_accuracy": 0.0,
            "avg_rt": 0.0,
            "last_accuracy": 0.0,
            "last_level": 1.0,
            "total_planets": 0.0,
        }

    def _load_user_progress(self, user_id: str) -> Dict[str, float]:
        lifetime_planets = self.auth_store.get_user_stat(user_id, "total_planets", 0.0)
        path = self.session_log_path
        if not path.exists():
            base = self._empty_progress()
            base["total_planets"] = lifetime_planets
            return base

        sessions = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("user_id") == user_id:
                    sessions.append(rec)

        if not sessions:
            base = self._empty_progress()
            base["total_planets"] = lifetime_planets
            return base

        avg_acc = sum(float(s.get("accuracy_total", 0.0)) for s in sessions) / len(sessions)
        best_acc = max(float(s.get("accuracy_total", 0.0)) for s in sessions)
        avg_rt = sum(float(s.get("mean_rt", 0.0)) for s in sessions) / len(sessions)
        last_acc = float(sessions[-1].get("accuracy_total", 0.0))
        last_level = float(sessions[-1].get("last_level", sessions[-1].get("max_level", 1)))
        sessions_planets = sum(float(s.get("planets_visited", 0.0)) for s in sessions)
        total_planets = max(lifetime_planets, sessions_planets)
        return {
            "sessions": float(len(sessions)),
            "avg_accuracy": avg_acc,
            "best_accuracy": best_acc,
            "avg_rt": avg_rt,
            "last_accuracy": last_acc,
            "last_level": last_level,
            "total_planets": total_planets,
        }

    def _load_recent_sessions(self, user_id: str, limit: int = 20) -> List[dict]:
        path = self.session_log_path
        if not path.exists():
            return []

        sessions: List[dict] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("user_id") == user_id:
                    sessions.append(rec)
        return sessions[-limit:]

    def _draw_wrapped_text(
        self,
        text: str,
        x: int,
        y: int,
        max_width: int,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        line_h: int,
    ) -> int:
        words = text.split()
        line = ""
        yy = y
        for word in words:
            candidate = f"{line} {word}".strip()
            if font.size(candidate)[0] <= max_width:
                line = candidate
                continue
            if line:
                self.screen.blit(font.render(line, True, color), (x, yy))
                yy += line_h
            line = word
        if line:
            self.screen.blit(font.render(line, True, color), (x, yy))
            yy += line_h
        return yy

    def _current_session_stats(self) -> Dict[str, float] | None:
        live = self._summarize_task_results(self.results)
        if live is not None:
            return live
        return self.saved_run_preview_stats

    @staticmethod
    def _summarize_task_results(results: List[TaskResult]) -> Dict[str, float] | None:
        if not results:
            return None
        tasks = len(results)
        accuracy = sum(1 for r in results if r.correct) / max(1, tasks)
        rts = [r.rt_ms for r in results if r.rt_ms is not None]
        mean_rt = (sum(rts) / len(rts)) if rts else 0.0
        return {"tasks": float(tasks), "accuracy": accuracy, "mean_rt": mean_rt}

    def _load_saved_run_preview_stats(self) -> Dict[str, float] | None:
        if not self.user_id:
            return None
        snapshot = self._load_pending_runs().get(self.user_id)
        if not isinstance(snapshot, dict):
            return None
        raw_results = snapshot.get("results", [])
        if not isinstance(raw_results, list):
            return None
        results: List[TaskResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            try:
                results.append(TaskResult(**item))
            except TypeError:
                continue
        return self._summarize_task_results(results)

    def _total_planets_overall(self) -> int:
        return int(self.user_progress.get("total_planets", 0.0))

    def _increment_total_planets(self, delta: int = 1) -> None:
        if not self.user_id or delta <= 0:
            return
        new_total = self.auth_store.increment_user_stat(self.user_id, "total_planets", float(delta))
        self.user_progress["total_planets"] = new_total

    @staticmethod
    def _empty_task_offsets() -> Dict[str, int]:
        return {
            "compare_codes": 0,
            "sequence_memory": 0,
            "rule_switch": 0,
            "parity_check": 0,
            "radar_scan": 0,
        }

    def _normalize_task_offsets(self, payload: object) -> Dict[str, int]:
        base = self._empty_task_offsets()
        if not isinstance(payload, dict):
            return base
        for key in base.keys():
            try:
                raw = int(payload.get(key, 0))
            except (TypeError, ValueError):
                raw = 0
            base[key] = self._clamp_task_offset(raw, self.current_level)
        return base

    @staticmethod
    def _tempo_bounds_for_level(level: int) -> tuple[int, int]:
        # Уровень — основной контур сложности, RL двигает темп только в допустимых пределах.
        if level <= 5:
            return -1, 1
        if level <= 8:
            return -2, 1
        return -2, 2

    @staticmethod
    def _task_offset_bounds_for_level(level: int) -> tuple[int, int]:
        # На низких уровнях не усложняем задачу, только можем смягчить.
        if level <= 3:
            return -1, 0
        return -1, 1

    def _clamp_tempo_for_level(self, tempo_offset: int, level: int) -> int:
        low, high = self._tempo_bounds_for_level(level)
        return max(low, min(high, int(tempo_offset)))

    def _clamp_task_offset(self, task_offset: int, level: int) -> int:
        low, high = self._task_offset_bounds_for_level(level)
        return max(low, min(high, int(task_offset)))

    def _build_effective_difficulty(self) -> DifficultyConfig:
        base_by_level = apply_level(self.base_difficulty, self.current_level)
        with_tempo = apply_tempo(base_by_level, self.tempo_offset)
        return apply_task_offsets(with_tempo, self.task_offsets)

    def _apply_task_deltas(self, deltas: Dict[str, int]) -> None:
        for key in self.task_offsets.keys():
            delta = 0
            if isinstance(deltas, dict):
                try:
                    delta = int(deltas.get(key, 0))
                except (TypeError, ValueError):
                    delta = 0
            cur = int(self.task_offsets.get(key, 0))
            self.task_offsets[key] = self._clamp_task_offset(cur + delta, self.current_level)

    def _relax_task_offsets_to_neutral(self) -> None:
        for key, value in list(self.task_offsets.items()):
            cur = int(value)
            if cur > 0:
                cur -= 1
            elif cur < 0:
                cur += 1
            self.task_offsets[key] = self._clamp_task_offset(cur, self.current_level)

    @staticmethod
    def _task_adjustment_state(state: list[float]) -> tuple[bool, bool, bool]:
        if len(state) < 6:
            return False, False, False
        try:
            acc = float(state[0])
            mean_rt = float(state[1])
            error_streak = float(state[3])
            fatigue_trend = float(state[5])
        except (TypeError, ValueError):
            return False, False, False

        struggle = (
            (acc <= 0.7 and mean_rt >= 1750.0)
            or (acc <= 0.65)
            or (mean_rt >= 2100.0)
            or (error_streak >= 1.0 and mean_rt >= 1500.0)
            or (fatigue_trend >= 150.0 and mean_rt >= 1700.0)
        )
        flow = (
            acc >= 0.9
            and mean_rt <= 1450.0
            and error_streak <= 0.0
            and fatigue_trend <= 90.0
        )
        recovered = (
            acc >= 0.875
            and mean_rt <= 1600.0
            and error_streak <= 0.0
            and fatigue_trend <= 120.0
        )
        return struggle, flow, recovered

    def _apply_task_offset_adaptation(self, state: list[float]) -> None:
        struggle, flow, recovered = self._task_adjustment_state(state)
        if struggle:
            self.task_struggle_streak += 1
            self.task_flow_streak = 0
            changed = False
            for key, value in list(self.task_offsets.items()):
                cur = int(value)
                if cur > -1:
                    self.task_offsets[key] = self._clamp_task_offset(cur - 1, self.current_level)
                    changed = True
            self.last_task_adjustment_reason = "struggle_soften" if changed else "struggle_hold"
            return
        self.task_struggle_streak = 0
        if flow:
            self.task_flow_streak += 1
        else:
            self.task_flow_streak = 0
        if self.task_flow_streak >= 2:
            changed = False
            for key, value in list(self.task_offsets.items()):
                cur = int(value)
                nxt = self._clamp_task_offset(cur + 1, self.current_level)
                if nxt != cur:
                    self.task_offsets[key] = nxt
                    changed = True
            if changed:
                self.task_flow_streak = 0
                self.last_task_adjustment_reason = "flow_harden"
            else:
                self.last_task_adjustment_reason = "flow_hold"
            return
        if recovered:
            before = dict(self.task_offsets)
            self._relax_task_offsets_to_neutral()
            self.last_task_adjustment_reason = "recovery_relax" if self.task_offsets != before else "recovery_hold"
            return
        self.last_task_adjustment_reason = "neutral"

    def _adaptation_profile_label(self) -> str:
        if self.tempo_offset <= -2:
            return "Адаптация: сильно мягче"
        if self.tempo_offset == -1:
            return "Адаптация: мягче"
        if self.tempo_offset == 0:
            return "Адаптация: стабильно"
        if self.tempo_offset == 1:
            return "Адаптация: интенсивнее"
        return "Адаптация: максимально интенсивно"

    def _task_profile_label(self) -> str:
        labels = {
            "compare_codes": "Коды",
            "sequence_memory": "Память",
            "rule_switch": "Правила",
            "parity_check": "Четность",
            "radar_scan": "Радар",
        }
        soft = [labels[k] for k, v in self.task_offsets.items() if int(v) < 0 and k in labels]
        hard = [labels[k] for k, v in self.task_offsets.items() if int(v) > 0 and k in labels]
        if not soft and not hard:
            return "Профиль задач: нейтрально"
        chunks: List[str] = []
        if soft:
            chunks.append("мягче: " + ",".join(soft[:2]))
        if hard:
            chunks.append("сложнее: " + ",".join(hard[:2]))
        return "Профиль задач: " + " | ".join(chunks)

    def _rl_warning(self) -> str:
        if self._rl_model_exists():
            return ""
        return "Агент не доступен, смена невозможна"

    def _effective_mode(self) -> str:
        if self.force_model_mode and self._rl_model_exists():
            return "ppo"
        return self.selected_mode

    def _model_version(self) -> str:
        return f"{self._effective_mode()}_v1"

    def _resolve_resource_path(self, rel_path: str) -> Path:
        path = Path(rel_path)
        if path.is_absolute() and path.exists():
            return path
        bundled_resource_candidate = bundled_resource_path(*path.parts)
        if bundled_resource_candidate.exists():
            return bundled_resource_candidate
        if len(path.parts) >= 2 and path.parts[0] == "data":
            bundled_candidate = bundled_data_path(*path.parts[1:])
        else:
            bundled_candidate = bundled_data_path(path.name)
        if bundled_candidate.exists():
            return bundled_candidate
        cwd_candidate = Path.cwd() / path
        if cwd_candidate.exists():
            return cwd_candidate
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            bundle_candidate = Path(meipass) / path
            if bundle_candidate.exists():
                return bundle_candidate
        return cwd_candidate

    def _rl_model_exists(self) -> bool:
        return self.rl_model_path.exists()

    def _render_feedback(self, now_ms: int) -> None:
        if now_ms - self.last_feedback_ms > self.last_feedback_duration_ms:
            return
        if self.last_feedback_text == "Слишком поздно":
            return
        color = self.ui.theme.accent if self.last_feedback_ok else self.ui.theme.alert
        words = self.last_feedback_text.split()
        lines: List[str] = []
        current = ""
        max_width = self.ui.center_panel.width - 40
        for word in words:
            candidate = f"{current} {word}".strip()
            if self.ui.font_mid.size(candidate)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if not lines:
            return

        line_h = self.ui.font_mid.get_height() + 4
        total_h = len(lines) * line_h
        start_y = self.ui.center_panel.centery - (total_h // 2)
        for idx, text_line in enumerate(lines):
            shadow = self.ui.font_mid.render(text_line, True, (10, 16, 28))
            text = self.ui.font_mid.render(text_line, True, color)
            rect = text.get_rect(center=(self.ui.center_panel.centerx, start_y + idx * line_h + line_h // 2))
            self.screen.blit(shadow, (rect.x + 2, rect.y + 2))
            self.screen.blit(text, rect)

    def _finalize_session(self) -> None:
        if self.persist_active_run_on_exit:
            return
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
        record = summary.__dict__.copy()
        record["user_id"] = self.user_id
        record["max_level"] = self.current_level
        record["last_level"] = self.current_level
        record["planets_visited"] = self.planets_visited
        record["task_offsets"] = dict(self.task_offsets)
        self.session_logger.write(record)
        self.telemetry.track(
            event_type="session_end",
            user_id=self.user_id,
            session_id=self.session_id,
            model_version=self._model_version(),
            payload=record,
        )
        self.telemetry.flush(force=True)
        self.partial_session_end_emitted = True
        self._clear_saved_run()
        if self.user_id:
            self.user_progress = self._load_user_progress(self.user_id)
            self.user_recent_sessions = self._load_recent_sessions(self.user_id)

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
        return task_title(task_id)

    def _encode_action(self, prev_level: int, prev_tempo: int) -> tuple:
        delta_level = max(-1, min(1, self.current_level - prev_level))
        delta_tempo = max(-1, min(1, self.tempo_offset - prev_tempo))
        action_id = (delta_level + 1) * 3 + (delta_tempo + 1)
        return action_id, delta_level, delta_tempo

    def _build_state(self, window: List[TaskResult]) -> list:
        g = self.current_difficulty.global_params
        return build_state_vector(
            window=window,
            current_level=self.current_level,
            event_rate_sec=g.event_rate_sec,
            time_pressure=g.time_pressure,
            parallel_streams=g.parallel_streams,
            task_mix=g.task_mix,
        )

    @staticmethod
    def _compute_reward(acc: float, mean_rt: float) -> float:
        return compute_reward(acc, mean_rt)

    def _current_zone_quality(self) -> float:
        batch = self.results[self.batch_result_start :]
        window = batch[-8:]
        return compute_zone_quality(window)

    def _current_flight_progress(self) -> float:
        successes = self._current_flight_successes()
        return compute_flight_progress(successes, self.session.total_tasks)

    def _current_flight_successes(self) -> int:
        current_batch = self.results[self.batch_result_start :]
        return count_successes(current_batch)

    @staticmethod
    def _compute_fatigue_trend(window: List[TaskResult]) -> float:
        return compute_fatigue_trend(window)

    @staticmethod
    def _compute_switch_cost(window: List[TaskResult]) -> float:
        return compute_switch_cost(window)

    def _start_next_batch(self) -> None:
        batch = self.results[self.batch_result_start :]
        if not batch:
            return

        answered = sum(1 for r in batch if not r.is_timeout)
        correct = sum(1 for r in batch if r.correct)

        if answered == 0:
            self.last_feedback_text = "Нет ответов. Нажми Старт, чтобы продолжить."
            self.current_difficulty = self._build_effective_difficulty()
            self.task_manager = TaskManager(
                self.current_difficulty,
                total_tasks=self.session.total_tasks,
                inter_task_pause_ms=self.session.inter_task_pause_ms,
                seed=self.task_manager.tasks_created + len(self.results) + 1,
            )
            self.task_manager.set_level(self.current_level)
            self.batch_result_start = len(self.results)
            self.batch_index += 1
            self.active_slot_index = None
            self.last_focused_token = None
            self.last_feedback_ms = pygame.time.get_ticks()
            self.last_feedback_duration_ms = 2200
            self.last_feedback_ok = False
            self._roll_motivation_phrase()
            self.started = False
            self.pause_menu_open = False
            self._save_active_run_snapshot()
            return

        self._maybe_adapt(batch)
        answer_rate = answered / max(1, self.session.total_tasks)
        answer_accuracy = (correct / answered) if answered > 0 else 0.0

        effective_mode = self._effective_mode()
        if effective_mode == "baseline":
            need = min(self.session.total_tasks, self.level_cfg.baseline_required_correct)
            level_up = correct >= need
            level_down = False
        else:
            level_up = answer_rate >= 0.75 and answer_accuracy >= 0.8
            level_down = answer_rate < 0.5 or answer_accuracy < 0.55

        did_level_up = False
        completed_stage_successfully = False
        if level_up:
            completed_stage_successfully = True
            if self.current_level < self.level_cfg.max_level:
                self.current_level += 1
                did_level_up = True
            elif effective_mode != "baseline":
                self.tempo_offset = self._clamp_tempo_for_level(self.tempo_offset + 1, self.current_level)
            if did_level_up:
                self.planets_visited += 1
                self._increment_total_planets(1)
                self.last_feedback_text = (
                    f"Ура, новый уровень! {correct}/{self.session.total_tasks} • Теперь: {self.current_level}"
                )
            elif effective_mode != "baseline":
                self.last_feedback_text = (
                    f"Уровень максимальный. Результат: {correct}/{self.session.total_tasks}."
                )
            else:
                self.last_feedback_text = (
                    f"Максимальный уровень {self.current_level}. Результат: {correct}/{self.session.total_tasks}."
                )
        elif level_down:
            self.current_level = max(self.level_cfg.min_level, self.current_level - 1)
            self.last_feedback_text = (
                f"Результат {correct}/{self.session.total_tasks}. Уровень снижен до {self.current_level}."
            )
        else:
            self.last_feedback_text = (
                f"Результат {correct}/{self.session.total_tasks}. Уровень не изменился."
            )

        self.tempo_offset = self._clamp_tempo_for_level(self.tempo_offset, self.current_level)
        self.current_difficulty = self._build_effective_difficulty()
        self.task_manager = TaskManager(
            self.current_difficulty,
            total_tasks=self.session.total_tasks,
            inter_task_pause_ms=self.session.inter_task_pause_ms,
            seed=self.task_manager.tasks_created + len(self.results) + 1,
        )
        self.task_manager.set_level(self.current_level)
        self.batch_result_start = len(self.results)
        self.batch_index += 1
        self.active_slot_index = None
        self.last_focused_token = None
        self.last_feedback_ms = pygame.time.get_ticks()
        self.last_feedback_duration_ms = 2200
        self.last_feedback_ok = True
        self._roll_motivation_phrase()
        if completed_stage_successfully and self.current_level >= self.level_cfg.max_level:
            self.last_feedback_text = ""
            self._open_max_level_popup()
        elif self.pause_between_levels and completed_stage_successfully:
            # После успешного этапа даем паузу даже на максимальном уровне,
            # иначе после достижения потолка сложности игра неожиданно идет без остановки.
            self.started = False
            self.pause_menu_open = False
        self._save_active_run_snapshot()
