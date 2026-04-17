"""PPO training loop for BVE parameter prediction.

Usage
-----
    cd <repo_root>
    python -m scripts.bve_rl.train [--iters N] [--batch B] [--ckpt-dir PATH]

Training loop (single-step contextual bandit, one episode = one AIG):
  1. Sample a batch of (aig, qdimacs) pairs from the training corpus.
  2. With no_grad: encode graphs → g; sample (p, p_raw, log_p, v) from policy.
  3. Run parallel BVE rollouts → rewards r.
  4. Compute advantages A = r − v; normalise.
  5. For ppo_epochs: recompute log_prob / entropy / value under current policy;
     compute PPO clipped loss; step optimiser.
  6. Log metrics; checkpoint every CKPT_EVERY iters; validate every VAL_EVERY.

Logging: mean_reward, entropy, value_loss, p_mean/std per dimension.
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import time
from typing import Optional

import numpy as np
import torch
from torch import Tensor
from torch_geometric.data import Batch, Data

from . import config
from .aig_parser import aig_to_pyg, build_aig_cache
from .corpus import CorpusEntry, build_corpus, split_corpus
from .model import BVEPolicy
from .rollout import parallel_rollout

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ── graph batching ────────────────────────────────────────────────────────────

def _entries_to_batch(
    entries: list[CorpusEntry],
    cache:   dict[str, Data],
) -> Batch:
    graphs = [cache[e.aig_path] for e in entries]
    return Batch.from_data_list(graphs).to(DEVICE)


# ── PPO update ────────────────────────────────────────────────────────────────

def _ppo_update(
    policy:       BVEPolicy,
    optimiser:    torch.optim.Optimizer,
    g:            Tensor,          # [B, hidden]  — already computed, no grad needed for g
    p_raw_old:    Tensor,          # [B, D]
    log_p_old:    Tensor,          # [B]
    advantages:   Tensor,          # [B]  normalised
    returns:      Tensor,          # [B]  = rewards (single-step, γ=1)
    ppo_epochs:   int = config.PPO_EPOCHS,
) -> dict[str, float]:
    """Run PPO_EPOCHS gradient steps and return log dict."""
    metrics: dict[str, list[float]] = {
        "policy_loss": [], "value_loss": [], "entropy": [], "total_loss": []
    }

    for _ in range(ppo_epochs):
        log_p_new, ent, v_new = policy.evaluate(g, p_raw_old)

        ratio  = (log_p_new - log_p_old.detach()).exp()
        clip_r = ratio.clamp(1.0 - config.CLIP_EPS, 1.0 + config.CLIP_EPS)
        l_clip = torch.min(ratio * advantages, clip_r * advantages).mean()

        l_value = (v_new - returns).pow(2).mean()
        l_ent   = ent.mean()
        loss    = -l_clip + config.VALUE_COEFF * l_value - config.ENTROPY_COEFF * l_ent

        optimiser.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(policy.parameters(), config.GRAD_CLIP)
        optimiser.step()

        metrics["policy_loss"].append(l_clip.item())
        metrics["value_loss"].append(l_value.item())
        metrics["entropy"].append(l_ent.item())
        metrics["total_loss"].append(loss.item())

    return {k: float(np.mean(v)) for k, v in metrics.items()}


# ── validation ────────────────────────────────────────────────────────────────

@torch.no_grad()
def _validate(
    policy:  BVEPolicy,
    entries: list[CorpusEntry],
    cache:   dict[str, Data],
    batch_size: int = config.BATCH_SIZE,
) -> float:
    """Return mean reward on the validation set (greedy / mean action)."""
    rewards_all: list[float] = []
    for start in range(0, len(entries), batch_size):
        batch_entries = entries[start: start + batch_size]
        bg   = _entries_to_batch(batch_entries, cache)
        g    = policy.encode(bg.x, bg.edge_index, bg.edge_attr, bg.batch)
        mean, _ = policy.actor.forward(g)
        p    = policy.actor._rescale(mean)          # deterministic action
        p_np = p.cpu().numpy()
        qdimacs = [e.qdimacs_path for e in batch_entries]
        r    = parallel_rollout(qdimacs, p_np)
        rewards_all.extend(r.tolist())
    return float(np.mean(rewards_all)) if rewards_all else 0.0


# ── checkpoint helpers ────────────────────────────────────────────────────────

def _save_checkpoint(
    policy:    BVEPolicy,
    optimiser: torch.optim.Optimizer,
    iteration: int,
    ckpt_dir:  str,
) -> None:
    os.makedirs(ckpt_dir, exist_ok=True)
    path = os.path.join(ckpt_dir, f"ckpt_{iteration:05d}.pt")
    torch.save(
        {"iteration": iteration,
         "model": policy.state_dict(),
         "optimiser": optimiser.state_dict()},
        path,
    )
    logger.info("Checkpoint saved: %s", path)


def _load_checkpoint(
    policy:    BVEPolicy,
    optimiser: Optional[torch.optim.Optimizer],
    path:      str,
) -> int:
    ckpt = torch.load(path, map_location=DEVICE)
    policy.load_state_dict(ckpt["model"])
    if optimiser is not None and "optimiser" in ckpt:
        optimiser.load_state_dict(ckpt["optimiser"])
    start = ckpt.get("iteration", 0) + 1
    logger.info("Resumed from %s (iter %d)", path, start)
    return start


# ── main training loop ────────────────────────────────────────────────────────

def train(
    num_iters: int        = config.NUM_ITERS,
    batch_size: int       = config.BATCH_SIZE,
    ckpt_dir: str         = "checkpoints/bve_rl",
    resume_from: Optional[str] = None,
) -> None:
    # ── corpus ────────────────────────────────────────────────────────────────
    logger.info("Building corpus …")
    all_entries = build_corpus()
    if not all_entries:
        raise RuntimeError("Empty corpus — check AIG_DIR and QDIMACS_SPD_DIR in config.py")
    train_entries, val_entries, test_entries = split_corpus(all_entries)

    logger.info("Pre-caching AIG graphs …")
    all_paths   = list({e.aig_path for e in all_entries})   # deduplicate
    graph_cache = build_aig_cache(all_paths)

    # Filter corpus to successfully parsed AIGs
    train_entries = [e for e in train_entries if e.aig_path in graph_cache]
    val_entries   = [e for e in val_entries   if e.aig_path in graph_cache]
    logger.info("After cache filter — train: %d  val: %d",
                len(train_entries), len(val_entries))

    # ── model + optimiser ─────────────────────────────────────────────────────
    policy    = BVEPolicy().to(DEVICE)
    optimiser = torch.optim.Adam(policy.parameters(), lr=config.LR)
    start_iter = 0
    if resume_from:
        start_iter = _load_checkpoint(policy, optimiser, resume_from)

    logger.info("Training on %s — %d params",
                DEVICE, sum(p.numel() for p in policy.parameters()))

    # ── training loop ─────────────────────────────────────────────────────────
    rng = random.Random(0)
    for iteration in range(start_iter, num_iters):
        t0 = time.time()

        # 1. Sample batch
        batch_entries = rng.choices(train_entries, k=batch_size)

        # 2. Encode + rollout collection (no grad)
        with torch.no_grad():
            bg = _entries_to_batch(batch_entries, graph_cache)
            g  = policy.encode(bg.x, bg.edge_index, bg.edge_attr, bg.batch)
            p, p_raw, log_p, v = policy.act(g)

        p_np = p.cpu().numpy()                                            # [B, D]
        qdimacs = [e.qdimacs_path for e in batch_entries]
        r_np = parallel_rollout(qdimacs, p_np)                           # [B] rewards

        # 3. Advantages
        r       = torch.tensor(r_np, dtype=torch.float, device=DEVICE)  # [B]
        adv     = r - v.detach()
        adv     = (adv - adv.mean()) / (adv.std() + 1e-8)

        # 4. PPO update
        update_metrics = _ppo_update(
            policy, optimiser, g.detach(), p_raw.detach(),
            log_p.detach(), adv.detach(), r.detach(),
        )

        elapsed = time.time() - t0

        # 5. Logging
        if iteration % 1 == 0:   # log every iteration
            p_mean = p_np.mean(axis=0)
            p_std  = p_np.std(axis=0)
            p_mean_str = " ".join(f"{v:.1f}" for v in p_mean)
            p_std_str  = " ".join(f"{v:.1f}" for v in p_std)
            logger.info(
                "iter %4d | r=%.4f | ent=%.3f | vl=%.4f | "
                "p_mean=[%s] | p_std=[%s] | %.1fs",
                iteration,
                r_np.mean(),
                update_metrics["entropy"],
                update_metrics["value_loss"],
                p_mean_str,
                p_std_str,
                elapsed,
            )

        # 6. Validation
        if (iteration + 1) % config.VAL_EVERY == 0 and val_entries:
            val_reward = _validate(policy, val_entries, graph_cache)
            logger.info(">>> val mean_reward = %.4f (iter %d)", val_reward, iteration)

        # 7. Checkpoint
        if (iteration + 1) % config.CKPT_EVERY == 0:
            _save_checkpoint(policy, optimiser, iteration, ckpt_dir)

    # Final checkpoint
    _save_checkpoint(policy, optimiser, num_iters - 1, ckpt_dir)
    logger.info("Training complete.")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Train BVE-RL policy (GNN + PPO)")
    parser.add_argument("--iters",     type=int,   default=config.NUM_ITERS)
    parser.add_argument("--batch",     type=int,   default=config.BATCH_SIZE)
    parser.add_argument("--ckpt-dir",  type=str,   default="checkpoints/bve_rl")
    parser.add_argument("--resume",    type=str,   default=None,
                        help="Path to checkpoint to resume from")
    args = parser.parse_args()
    train(
        num_iters=args.iters,
        batch_size=args.batch,
        ckpt_dir=args.ckpt_dir,
        resume_from=args.resume,
    )


if __name__ == "__main__":
    main()
