from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Optional, Tuple


@dataclass
class RLAgent:
    model_path: str
    action_dim: int = 3
    action_space: str = "tempo3"
    task_heads: tuple[str, ...] = (
        "compare_codes",
        "sequence_memory",
        "rule_switch",
        "parity_check",
        "radar_scan",
    )
    last_task_deltas: dict[str, int] | None = None
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
                if action_dim in (3, 9, 18):
                    self.action_dim = action_dim
                action_space = str(meta.get("action_space", self.action_space)).strip()
                if action_space:
                    self.action_space = action_space
                heads = meta.get("task_heads")
                if isinstance(heads, list) and heads:
                    self.task_heads = tuple(str(h) for h in heads)
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
            self.last_task_deltas = {k: 0 for k in self.task_heads}
            return 1, 0, 0
        neutral_action = 1  # tempo-only action space: 0/1/2 -> -1/0/+1
        try:
            if self.model is None:
                self.load(len(state))
            if self.model is None:
                self.last_task_deltas = {k: 0 for k in self.task_heads}
                return neutral_action, 0, 0
            x = torch.tensor([state], dtype=torch.float32)
            with torch.no_grad():
                logits, _ = self.model(x)
                logits = logits.squeeze(0)
                if self.action_space == "tempo3_task_offsets_v1" and int(logits.shape[0]) >= 18:
                    tempo_logits = logits[:3]
                    action_id = int(torch.argmax(tempo_logits).item())
                    task_deltas: dict[str, int] = {}
                    for head_idx, head_name in enumerate(self.task_heads[:5]):
                        start = 3 + head_idx * 3
                        head_logits = logits[start : start + 3]
                        if int(head_logits.shape[0]) < 3:
                            task_deltas[head_name] = 0
                            continue
                        head_action = int(torch.argmax(head_logits).item())
                        task_deltas[head_name] = head_action - 1
                    self.last_task_deltas = task_deltas
                else:
                    action_id = int(torch.argmax(logits, dim=-1).item())
                    self.last_task_deltas = {k: 0 for k in self.task_heads}
            self.available = True
        except Exception:
            self.available = False
            self.last_task_deltas = {k: 0 for k in self.task_heads}
            return neutral_action, 0, 0
        if self.action_dim == 9:
            # Совместимость со старой моделью 3x3.
            delta_tempo = (action_id % 3) - 1
        else:
            delta_tempo = action_id - 1
            delta_tempo = max(-1, min(1, delta_tempo))
        delta_level = 0
        return action_id, delta_level, delta_tempo
