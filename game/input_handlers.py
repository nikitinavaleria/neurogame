from __future__ import annotations

import pygame


def handle_auth_event(app, event: pygame.event.Event) -> None:
    if event.type != pygame.KEYDOWN:
        return
    if event.key == pygame.K_TAB:
        app.auth_focus = "password" if app.auth_focus == "username" else "username"
        return
    if event.key in (pygame.K_F2, pygame.K_m):
        app.auth_mode = "register" if app.auth_mode == "login" else "login"
        app.auth_message = "Режим: регистрация" if app.auth_mode == "register" else "Режим: вход"
        return
    if event.key == pygame.K_RETURN:
        app._submit_auth()
        return
    if event.key == pygame.K_BACKSPACE:
        if app.auth_focus == "username":
            app.auth_username = app.auth_username[:-1]
        else:
            app.auth_password = app.auth_password[:-1]
        return
    if not event.unicode or not event.unicode.isprintable():
        return
    char = event.unicode
    if app.auth_focus == "username":
        if len(app.auth_username) >= 24:
            return
        if char.isalnum() or char in "._-":
            app.auth_username += char
    else:
        if len(app.auth_password) < 32:
            app.auth_password += char


def handle_auth_mouse(app, pos: tuple[int, int]) -> None:
    if app.auth_username_rect and app.auth_username_rect.collidepoint(pos):
        app.auth_focus = "username"
        return
    if app.auth_password_rect and app.auth_password_rect.collidepoint(pos):
        app.auth_focus = "password"
        return
    if app.auth_toggle_rect and app.auth_toggle_rect.collidepoint(pos):
        app.auth_mode = "register" if app.auth_mode == "login" else "login"
        app.auth_message = "Режим: регистрация" if app.auth_mode == "register" else "Режим: вход"
        return
    if app.auth_submit_rect and app.auth_submit_rect.collidepoint(pos):
        app._submit_auth()
        return


def handle_menu_mouse(app, pos: tuple[int, int]) -> None:
    if app.telemetry_url_rect and app.telemetry_url_rect.collidepoint(pos):
        app.telemetry_input_focused = True
        return
    app.telemetry_input_focused = False
    if app.telemetry_check_rect and app.telemetry_check_rect.collidepoint(pos):
        app._check_telemetry_connection()
        return
    if app.telemetry_save_rect and app.telemetry_save_rect.collidepoint(pos):
        app._save_telemetry_url()
        return
    if app.resume_button_rect and app.resume_button_rect.collidepoint(pos):
        if not app.awaiting_run_setup:
            app.started = True
            return
        if app.awaiting_run_setup and app._restore_saved_run():
            return
        level = int(app.user_progress.get("last_level", 1))
        app._begin_user_run(max(1, level))
        return
    if app.restart_button_rect and app.restart_button_rect.collidepoint(pos):
        app._begin_user_run(1)
        return
    if app.start_button_rect and app.start_button_rect.collidepoint(pos):
        if app.awaiting_run_setup:
            app._begin_user_run(1)
        else:
            app.started = True
        return
    if app.menu_button_rect and app.menu_button_rect.collidepoint(pos):
        app._pause_run(open_pause_menu=True)
        return
    if app.mode_toggle_rect and app.mode_toggle_rect.collidepoint(pos):
        if app.selected_mode == "baseline":
            if app._rl_model_exists():
                app.selected_mode = "ppo"
        else:
            app.selected_mode = "baseline"
        return
    if app.level_transition_toggle_rect and app.level_transition_toggle_rect.collidepoint(pos):
        app.pause_between_levels = not app.pause_between_levels
        return
    if app.logout_button_rect and app.logout_button_rect.collidepoint(pos):
        app._logout_user()
        return
    if app.exit_button_rect and app.exit_button_rect.collidepoint(pos):
        app._exit_app()
        return


def handle_pause_menu_mouse(app, pos: tuple[int, int]) -> None:
    if app.resume_button_rect and app.resume_button_rect.collidepoint(pos):
        app.pause_menu_open = False
        app.started = True
        app.telemetry.track(
            event_type="session_resume",
            user_id=app.user_id,
            session_id=app.session_id,
            model_version=f"{app.selected_mode}_v1",
            payload={
                "session_id": app.session_id,
                "user_id": app.user_id,
                "mode": app.selected_mode,
                "source": "pause_menu_button",
            },
        )
        return
    if app.menu_button_rect and app.menu_button_rect.collidepoint(pos):
        app.pause_menu_open = False
        app.started = False
        app._save_active_run_snapshot()
        return
    if app.restart_button_rect and app.restart_button_rect.collidepoint(pos):
        app._begin_user_run(1)
        return
    if app.logout_button_rect and app.logout_button_rect.collidepoint(pos):
        app._logout_user()
        return
    if app.exit_button_rect and app.exit_button_rect.collidepoint(pos):
        app._exit_app()
        return


def handle_telemetry_event(app, event: pygame.event.Event) -> bool:
    if not app.telemetry_input_focused:
        return False
    if event.type != pygame.KEYDOWN:
        return False
    if event.key == pygame.K_RETURN:
        app._save_telemetry_url()
        return True
    if event.key == pygame.K_ESCAPE:
        app.telemetry_input_focused = False
        return True
    if event.key == pygame.K_BACKSPACE:
        app.telemetry_url_value = app.telemetry_url_value[:-1]
        return True
    if not event.unicode or not event.unicode.isprintable():
        return False
    if len(app.telemetry_url_value) >= 220:
        return True
    app.telemetry_url_value += event.unicode
    return True
