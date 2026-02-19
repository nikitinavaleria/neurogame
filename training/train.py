import argparse
import json
from pathlib import Path

import torch
import torch.nn.functional as F

from game.settings import SessionConfig
from training.dataset import build_transitions, load_adaptations
from training.model import ActorCritic


def parse_args():
    parser = argparse.ArgumentParser(description="Train adaptation model from adaptations.jsonl")
    parser.add_argument("--data", default="training/data/adaptations.jsonl")
    parser.add_argument("--out", default=SessionConfig().rl_model_path)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--gamma", type=float, default=0.97)
    parser.add_argument("--mode", choices=["all", "baseline", "ppo"], default="all")
    return parser.parse_args()


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    project_root = Path(__file__).resolve().parents[1]
    candidate = project_root / p
    if candidate.exists():
        return candidate
    return Path.cwd() / p


def main():
    args = parse_args()
    data_path = _resolve_path(args.data)
    out_path = _resolve_path(args.out)
    records = load_adaptations(str(data_path))
    modes = None if args.mode == "all" else {args.mode}
    transitions = build_transitions(records, modes=modes)
    if not transitions:
        print(f"No adaptations found at {data_path}. Play the game to generate data.")
        return

    state_dim = len(transitions[0].state)
    action_dim = 3  # tempo-only: [-1, 0, +1]
    model = ActorCritic(state_dim, action_dim)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    states = torch.tensor([t.state for t in transitions], dtype=torch.float32)
    actions = torch.tensor([t.action for t in transitions], dtype=torch.int64)
    rewards = torch.tensor([t.reward for t in transitions], dtype=torch.float32)
    next_states = torch.tensor([t.next_state for t in transitions], dtype=torch.float32)
    dones = torch.tensor([1.0 if t.done else 0.0 for t in transitions], dtype=torch.float32)

    n = states.size(0)
    for epoch in range(args.epochs):
        perm = torch.randperm(n)
        epoch_loss = 0.0
        batches = 0
        for start in range(0, n, args.batch_size):
            idx = perm[start : start + args.batch_size]
            s = states[idx]
            a = actions[idx]
            r = rewards[idx]
            ns = next_states[idx]
            d = dones[idx]

            logits, values = model(s)
            with torch.no_grad():
                _, next_values = model(ns)
            td_target = r + args.gamma * next_values * (1.0 - d)
            advantages = td_target - values
            norm_adv = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

            log_probs = F.log_softmax(logits, dim=-1)
            chosen = log_probs.gather(1, a.unsqueeze(1)).squeeze(1)
            policy_loss = -(chosen * norm_adv.detach()).mean()
            value_loss = F.mse_loss(values, td_target.detach())
            entropy = -(torch.exp(log_probs) * log_probs).sum(dim=-1).mean()
            loss = policy_loss + 0.5 * value_loss - 0.01 * entropy

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item())
            batches += 1

        print(f"Epoch {epoch + 1} loss={epoch_loss / max(1, batches):.4f}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), str(out_path))
    meta_path = out_path.with_suffix(".meta.json")
    meta = {
        "state_dim": state_dim,
        "action_dim": action_dim,
        "action_space": "tempo3",
        "transitions": n,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "gamma": args.gamma,
        "mode_filter": args.mode,
        "data_path": str(data_path),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved model to {out_path}")
    print(f"Saved metadata to {meta_path}")


if __name__ == "__main__":
    main()
