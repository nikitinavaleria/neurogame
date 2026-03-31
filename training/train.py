import argparse
import json
import math
from pathlib import Path

import torch
import torch.nn.functional as F

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


def _build_session_split(transitions: list, val_ratio: float = 0.15) -> tuple[torch.Tensor, torch.Tensor]:
    session_ids = sorted({str(t.session_id or "") for t in transitions})
    if len(session_ids) < 2:
        idx = torch.arange(len(transitions), dtype=torch.int64)
        return idx, idx[:0]
    val_count = max(1, int(math.ceil(len(session_ids) * val_ratio)))
    val_sessions = set(session_ids[-val_count:])
    train_idx = [i for i, t in enumerate(transitions) if str(t.session_id or "") not in val_sessions]
    val_idx = [i for i, t in enumerate(transitions) if str(t.session_id or "") in val_sessions]
    if not train_idx or not val_idx:
        idx = torch.arange(len(transitions), dtype=torch.int64)
        return idx, idx[:0]
    return torch.tensor(train_idx, dtype=torch.int64), torch.tensor(val_idx, dtype=torch.int64)


def _normalize_states(states: torch.Tensor, next_states: torch.Tensor, train_idx: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    train_states = states[train_idx]
    mean = train_states.mean(dim=0)
    std = train_states.std(dim=0, unbiased=False)
    std = torch.where(std < 1e-6, torch.ones_like(std), std)
    norm_states = (states - mean) / std
    norm_next_states = (next_states - mean) / std
    return norm_states, norm_next_states, mean, std


def _evaluate_epoch(
    model: ActorCritic,
    target_model: ActorCritic,
    states: torch.Tensor,
    actions: torch.Tensor,
    task_actions: torch.Tensor,
    rewards: torch.Tensor,
    next_states: torch.Tensor,
    dones: torch.Tensor,
    idx: torch.Tensor,
    gamma: float,
    cql_alpha: float,
) -> tuple[float, float, float, float]:
    if idx.numel() == 0:
        return 0.0, 0.0, 0.0, 0.0
    with torch.no_grad():
        s = states[idx]
        a = actions[idx]
        ta = task_actions[idx]
        r = rewards[idx]
        ns = next_states[idx]
        d = dones[idx]
        q_values_all, _ = model(s)
        q_values = q_values_all[:, :3]
        q_next_all, _ = target_model(ns)
        q_next = q_next_all[:, :3]
        next_v = q_next.max(dim=1).values
        td_target = r + gamma * next_v * (1.0 - d)
        q_taken = q_values.gather(1, a.unsqueeze(1)).squeeze(1)
        td_loss = F.smooth_l1_loss(q_taken, td_target)
        cql_loss = torch.logsumexp(q_values, dim=1).mean() - q_taken.mean()
        task_heads = int(task_actions.size(1)) if task_actions.ndim == 2 else 0
        task_loss = torch.tensor(0.0, dtype=torch.float32)
        if task_heads > 0:
            reward_weight = 1.0 + torch.clamp(r, min=-0.5, max=1.5)
            for head_idx in range(task_heads):
                start_col = 3 + (head_idx * 3)
                end_col = start_col + 3
                head_logits = q_values_all[:, start_col:end_col]
                ce = F.cross_entropy(head_logits, ta[:, head_idx], reduction="none")
                task_loss = task_loss + torch.mean(ce * reward_weight)
            task_loss = task_loss / task_heads
        loss = td_loss + (cql_alpha * cql_loss) + (0.25 * task_loss)
        return float(loss.item()), float(td_loss.item()), float(cql_loss.item()), float(task_loss.item())


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

    states = torch.tensor([t.state for t in transitions], dtype=torch.float32)
    actions = torch.tensor([t.action for t in transitions], dtype=torch.int64)
    task_actions = torch.tensor([t.task_actions for t in transitions], dtype=torch.int64)
    rewards = torch.tensor([t.reward for t in transitions], dtype=torch.float32)
    next_states = torch.tensor([t.next_state for t in transitions], dtype=torch.float32)
    dones = torch.tensor([1.0 if t.done else 0.0 for t in transitions], dtype=torch.float32)
    train_idx, val_idx = _build_session_split(transitions)
    states, next_states, state_mean, state_std = _normalize_states(states, next_states, train_idx)
    task_heads = int(task_actions.size(1)) if task_actions.ndim == 2 else 0
    action_dim = 3 + (task_heads * 3)
    model = ActorCritic(state_dim, action_dim)
    target_model = ActorCritic(state_dim, action_dim)
    target_model.load_state_dict(model.state_dict())
    target_model.eval()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    best_metric = float("inf")
    best_state_dict = None
    n = int(train_idx.numel())
    for epoch in range(args.epochs):
        perm = train_idx[torch.randperm(n)]
        epoch_loss = 0.0
        epoch_td_loss = 0.0
        epoch_cql_loss = 0.0
        epoch_task_loss = 0.0
        batches = 0
        for start in range(0, n, args.batch_size):
            idx = perm[start : start + args.batch_size]
            s = states[idx]
            a = actions[idx]
            ta = task_actions[idx]
            r = rewards[idx]
            ns = next_states[idx]
            d = dones[idx]

            q_values_all, _ = model(s)
            q_values = q_values_all[:, :3]
            with torch.no_grad():
                q_next_all, _ = target_model(ns)
                q_next = q_next_all[:, :3]
                next_v = q_next.max(dim=1).values
                td_target = r + args.gamma * next_v * (1.0 - d)

            q_taken = q_values.gather(1, a.unsqueeze(1)).squeeze(1)
            td_loss = F.smooth_l1_loss(q_taken, td_target)
            cql_loss = torch.logsumexp(q_values, dim=1).mean() - q_taken.mean()
            task_loss = torch.tensor(0.0, dtype=torch.float32)
            if task_heads > 0:
                reward_weight = 1.0 + torch.clamp(r, min=-0.5, max=1.5)
                for head_idx in range(task_heads):
                    start_col = 3 + (head_idx * 3)
                    end_col = start_col + 3
                    head_logits = q_values_all[:, start_col:end_col]
                    ce = F.cross_entropy(head_logits, ta[:, head_idx], reduction="none")
                    task_loss = task_loss + torch.mean(ce * reward_weight)
                task_loss = task_loss / task_heads
            loss = td_loss + (args.cql_alpha * cql_loss) + (0.25 * task_loss)

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
            epoch_task_loss += float(task_loss.item())
            batches += 1

        avg_loss = epoch_loss / max(1, batches)
        avg_td = epoch_td_loss / max(1, batches)
        avg_cql = epoch_cql_loss / max(1, batches)
        avg_task = epoch_task_loss / max(1, batches)
        val_total, val_td, val_cql, val_task = _evaluate_epoch(
            model=model,
            target_model=target_model,
            states=states,
            actions=actions,
            task_actions=task_actions,
            rewards=rewards,
            next_states=next_states,
            dones=dones,
            idx=val_idx,
            gamma=args.gamma,
            cql_alpha=args.cql_alpha,
        )
        metric = val_total if val_idx.numel() > 0 else avg_loss
        if metric < best_metric:
            best_metric = metric
            best_state_dict = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        if val_idx.numel() > 0:
            print(
                f"Epoch {epoch + 1} train_total={avg_loss:.4f} "
                f"train_td={avg_td:.4f} train_cql={avg_cql:.4f} train_task={avg_task:.4f} "
                f"val_total={val_total:.4f} val_td={val_td:.4f} val_cql={val_cql:.4f} val_task={val_task:.4f}"
            )
        else:
            print(
                f"Epoch {epoch + 1} total={avg_loss:.4f} "
                f"td={avg_td:.4f} cql={avg_cql:.4f} task={avg_task:.4f}"
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    final_state = best_state_dict or model.state_dict()
    torch.save(final_state, str(out_path))
    meta_path = out_path.with_suffix(".meta.json")
    meta = {
        "state_dim": state_dim,
        "action_dim": action_dim,
        "action_space": "tempo3_task_offsets_v1",
        "task_heads": ["compare_codes", "sequence_memory", "rule_switch", "parity_check", "radar_scan"],
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
        "train_transitions": int(train_idx.numel()),
        "val_transitions": int(val_idx.numel()),
        "selection_metric": "val_total" if val_idx.numel() > 0 else "train_total",
        "best_metric": best_metric,
        "state_mean": [float(x) for x in state_mean.tolist()],
        "state_std": [float(x) for x in state_std.tolist()],
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved model to {out_path}")
    print(f"Saved metadata to {meta_path}")


if __name__ == "__main__":
    main()
