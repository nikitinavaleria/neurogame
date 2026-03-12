from game.settings import DifficultyConfig, SessionConfig, WindowConfig
from game.app import GameApp
from game.runtime.env_loader import load_env_defaults


def main() -> None:
    load_env_defaults()
    app = GameApp(WindowConfig(), SessionConfig(), DifficultyConfig())
    app.run()


if __name__ == "__main__":
    main()
