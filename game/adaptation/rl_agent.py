from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Optional, Tuple


@dataclass
class RLAgent:
    model_path: str
    action_dim: int = 3
    state_dim: Optional[int] = None
    model: Optional[Any] = None
    available: bool = True

    def load(self, state_dim: int) -> None:
        try:
            import torch  # type: ignore
            from training.model import ActorCritic  # type: ignore
        except Exception as exc:
            self.available = False
            raise RuntimeError("torch_or_model_unavailable") from exc

        meta_path = Path(self.model_path).with_suffix(".meta.json")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                action_dim = int(meta.get("action_dim", self.action_dim))
                if action_dim in (3, 9):
                    self.action_dim = action_dim
            except Exception:
                pass
        self.state_dim = state_dim
        self.model = ActorCritic(state_dim, self.action_dim)
        self.model.load_state_dict(torch.load(self.model_path, map_location="cpu"))
        self.model.eval()
        self.available = True

    def act(self, state) -> Tuple[int, int, int]:
        try:
            import torch  # type: ignore
        except Exception:
            self.available = False
            return 1, 0, 0
        neutral_action = 1  # tempo-only action space: 0/1/2 -> -1/0/+1
        try:
            if self.model is None:
                self.load(len(state))
            if self.model is None:
                return neutral_action, 0, 0
            x = torch.tensor([state], dtype=torch.float32)
            with torch.no_grad():
                logits, _ = self.model(x)
                action_id = int(torch.argmax(logits, dim=-1).item())
            self.available = True
        except Exception:
            self.available = False
            return neutral_action, 0, 0
        if self.action_dim == 9:
            # Совместимость со старой моделью 3x3.
            delta_tempo = (action_id % 3) - 1
        else:
            delta_tempo = action_id - 1
            delta_tempo = max(-1, min(1, delta_tempo))
        delta_level = 0
        return action_id, delta_level, delta_tempo
