from dataclasses import dataclass
import random

COLORS = ["red", "green", "blue", "yellow"]
SHAPES = ["circle", "triangle", "square", "cross"]

TASK_COLOR = "COLOR"
TASK_SHAPE = "SHAPE"

ACTIONS = ["F", "J", "K", "L"]

@dataclass(frozen=True)
class Stimulus:
    color: str
    shape: str
    stimulus_id: str

def build_default_mapping() -> dict:
    return {TASK_COLOR: {"red": "F", "green": "J", "blue": "K", "yellow": "L"},
            TASK_SHAPE: {"circle": "F", "triangle": "J", "square": "K", "cross": "L"}}

def sample_stimulus(rng: random.Random, params=None) -> Stimulus:
    color = rng.choice(COLORS)
    shape = rng.choice(SHAPES)
    return Stimulus(color=color, shape=shape, stimulus_id=f"{color}_{shape}")

def get_correct_action(task_id: str, stimulus: Stimulus, mapping: dict) -> str:
    if task_id == TASK_COLOR:
        return mapping[TASK_COLOR][stimulus.color]
    if task_id == TASK_SHAPE:
        return mapping[TASK_SHAPE][stimulus.shape]
    raise ValueError(f"Unsupported task_id: {task_id}")


if __name__ =='__main__':
    rng = random.Random(42)
    mapping = build_default_mapping()

    stim = sample_stimulus(rng)
    action_color = get_correct_action('COLOR', stim, mapping)
    action_shape = get_correct_action('SHAPE', stim, mapping)

    print(stim, action_color, action_shape)

