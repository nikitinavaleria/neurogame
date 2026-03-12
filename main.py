import sys
import time
import traceback

from game.settings import DifficultyConfig, SessionConfig, WindowConfig
from game.app import GameApp
from game.runtime.paths import app_data_path

try:
    from game.runtime.env_loader import load_env_defaults
except ModuleNotFoundError:
    def load_env_defaults() -> None:
        # Keep startup resilient even if optional env loader was not bundled.
        return


def _log_fatal_startup_error(exc: Exception) -> None:
    payload = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    log_path = app_data_path("client_errors.log")
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"\n[{int(time.time())}] stage=startup\n{payload}\n")
    except OSError:
        pass


def main() -> None:
    try:
        load_env_defaults()
        app = GameApp(WindowConfig(), SessionConfig(), DifficultyConfig())
        app.run()
    except Exception as exc:
        _log_fatal_startup_error(exc)
        print("Fatal startup error. Check client_errors.log in app data directory.", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
