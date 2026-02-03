import math
from typing import List

import torch
import torch.nn.functional as F

from training.dataset import Transition, build_transitions, load_adaptations
from training.model import ActorCritic


def main():
    records = load_adaptations("data/adaptations.jsonl")
    transitions = build_transitions(records)
    if not transitions:
        print("No adaptations found. Play the game to generate data.")
        return

    state_dim = len(transitions[0].state)
    action_dim = 9  # 3x3
    model = ActorCritic(state_dim, action_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-4)

    states = torch.tensor([t.state for t in transitions], dtype=torch.float32)
    actions = torch.tensor([t.action for t in transitions], dtype=torch.int64)
    rewards = torch.tensor([t.reward for t in transitions], dtype=torch.float32)

    for epoch in range(10):
        logits, values = model(states)
        log_probs = F.log_softmax(logits, dim=-1)
        chosen = log_probs.gather(1, actions.unsqueeze(1)).squeeze(1)

        advantages = rewards - values.detach()
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        policy_loss = -(chosen * advantages).mean()
        value_loss = F.mse_loss(values, rewards)
        loss = policy_loss + 0.5 * value_loss

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        print(f"Epoch {epoch+1} loss={loss.item():.4f}")

    torch.save(model.state_dict(), "data/ppo_agent.pt")
    print("Saved model to data/ppo_agent.pt")


if __name__ == "__main__":
    main()
