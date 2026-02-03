from dataclasses import dataclass
from typing import Optional, Tuple

import torch

from training.model import ActorCritic


@dataclass
class RLAgent:
    model_path: str
    action_dim: int = 9
    state_dim: Optional[int] = None
    model: Optional[ActorCritic] = None

    def load(self, state_dim: int) -> None:
        self.state_dim = state_dim
        self.model = ActorCritic(state_dim, self.action_dim)
        self.model.load_state_dict(torch.load(self.model_path, map_location="cpu"))
        self.model.eval()

    def act(self, state) -> Tuple[int, int, int]:
        if self.model is None:
            self.load(len(state))
        x = torch.tensor([state], dtype=torch.float32)
        with torch.no_grad():
            logits, _ = self.model(x)
            action_id = int(torch.argmax(logits, dim=-1).item())
        delta_level = (action_id // 3) - 1
        delta_tempo = (action_id % 3) - 1
        return action_id, delta_level, delta_tempo
