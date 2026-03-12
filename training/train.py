import argparse
import json
from pathlib import Path

import torch

from game.settings import SessionConfig
from training.dataset import build_transitions, load_adaptations
from training.model import ActorCritic

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def parse_args():
    parser = argparse.ArgumentParser(description="Train offline tempo policy from adaptations.jsonl (CQL-style)")
    parser.add_argument("--data", default="training/data/adaptations.jsonl")
    parser.add_argument("--out", default=SessionConfig().rl_model_path)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--gamma", type=float, default=0.97)
    parser.add_argument("--mode", choices=["all", "baseline", "ppo"], default="all")
    parser.add_argument("--cql-alpha", type=float, default=1.0)
    parser.add_argument("--target-tau", type=float, default=0.02)
    return parser.parse_args()


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


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
    target_model = ActorCritic(state_dim, action_dim)
    target_model.load_state_dict(model.state_dict())
    target_model.eval()
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
        epoch_td_loss = 0.0
        epoch_cql_loss = 0.0
        batches = 0
        for start in range(0, n, args.batch_size):
            idx = perm[start : start + args.batch_size]
            s = states[idx]
            a = actions[idx]
            r = rewards[idx]
            ns = next_states[idx]
            d = dones[idx]

            q_values, _ = model(s)
            with torch.no_grad():
                q_next, _ = target_model(ns)
                next_v = q_next.max(dim=1).values
                td_target = r + args.gamma * next_v * (1.0 - d)

            q_taken = q_values.gather(1, a.unsqueeze(1)).squeeze(1)
            td_loss = torch.mean((q_taken - td_target) ** 2)
            cql_loss = torch.logsumexp(q_values, dim=1).mean() - q_taken.mean()
            loss = td_loss + (args.cql_alpha * cql_loss)

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()

            with torch.no_grad():
                for target_param, param in zip(target_model.parameters(), model.parameters()):
                    target_param.mul_(1.0 - args.target_tau).add_(args.target_tau * param)

            epoch_loss += float(loss.item())
            epoch_td_loss += float(td_loss.item())
            epoch_cql_loss += float(cql_loss.item())
            batches += 1

        avg_loss = epoch_loss / max(1, batches)
        avg_td = epoch_td_loss / max(1, batches)
        avg_cql = epoch_cql_loss / max(1, batches)
        print(
            f"Epoch {epoch + 1} total={avg_loss:.4f} "
            f"td={avg_td:.4f} cql={avg_cql:.4f}"
        )

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
        "algo": "offline_cql_q_learning",
        "cql_alpha": args.cql_alpha,
        "target_tau": args.target_tau,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved model to {out_path}")
    print(f"Saved metadata to {meta_path}")


if __name__ == "__main__":
    main()
