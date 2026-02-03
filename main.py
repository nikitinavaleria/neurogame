from config.settings import DifficultyConfig, SessionConfig, WindowConfig
from game.app import GameApp


def main() -> None:
    app = GameApp(WindowConfig(), SessionConfig(), DifficultyConfig())
    app.run()


if __name__ == "__main__":
    main()
