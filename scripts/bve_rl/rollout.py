"""BVE rollout: subprocess wrapper + parallel execution.

Interface
---------
rollout(qdimacs_path, p) -> float
    Run preprocess with parameters p on qdimacs_path.
    Returns composite reward (see below).

parallel_rollout(qdimacs_paths, p_batch) -> np.ndarray[float, B]
    Run B rollouts in parallel via multiprocessing.Pool.

Composite reward
----------------
    r = r_elim  −  α · t_norm  −  β · p_norm_mean

where:
    r_elim     = (vars_before − vars_after) / vars_before  ∈ [0, 1]
    t_norm     = elapsed / ROLLOUT_TIMEOUT                  ∈ [0, 1]
    p_norm_mean = mean((p_i − p_min_i) / (p_max_i − p_min_i)) ∈ [0, 1]
    α          = TIME_PENALTY_COEFF   (config, default 0.10)
    β          = PARAM_PENALTY_COEFF  (config, default 0.05)

Elimination fraction is the primary signal; time and parameter-scale
penalties discourage the policy from using unnecessarily large or slow
parameter configurations when the elimination fraction is equal.

vars_before / vars_after are derived by parsing the QDIMACS files directly
so the reward is independent of the binary's stdout format.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import time
from multiprocessing import Pool
from typing import NamedTuple

import numpy as np

from . import config

# Pre-computed bound arrays for fast param normalisation (module-level, read-only)
_P_MIN = np.array([b[0] for b in config.PARAM_BOUNDS], dtype=np.float64)
_P_MAX = np.array([b[1] for b in config.PARAM_BOUNDS], dtype=np.float64)
_P_RANGE = _P_MAX - _P_MIN   # avoids repeated subtraction in the hot path


# ── QDIMACS helpers ───────────────────────────────────────────────────────────

def _count_existential_vars(qdimacs_path: str) -> set[int]:
    """Return the set of existential variable indices from the 'e' block."""
    e_vars: set[int] = set()
    with open(qdimacs_path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] == 'c':
                continue
            if line[0] == 'e':
                for tok in line.split()[1:]:
                    if tok == '0':
                        break
                    e_vars.add(int(tok))
    return e_vars


def _vars_in_clauses(qdimacs_path: str) -> set[int]:
    """Return the set of all variable indices appearing in clause lines."""
    seen: set[int] = set()
    with open(qdimacs_path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in ('c', 'p', 'e', 'a'):
                continue
            for tok in line.split():
                v = int(tok)
                if v != 0:
                    seen.add(abs(v))
    return seen


# ── parameter serialisation ───────────────────────────────────────────────────

def _serialize_params(p: np.ndarray) -> list[str]:
    """Convert parameter vector to CLI flags for the preprocess binary."""
    args: list[str] = []
    for name, val in zip(config.PARAM_NAMES, p):
        int_val = max(1, int(round(float(val))))
        args.append(f"--{name}={int_val}")
    return args


# ── single rollout ────────────────────────────────────────────────────────────

def rollout(qdimacs_path: str, p: np.ndarray) -> float:
    """Run BVE with parameter vector *p* on *qdimacs_path*.

    Returns composite reward (see module docstring).
    Returns 0.0 on timeout, preprocess failure, or degenerate input.
    """
    # ── param-scale penalty (computed before subprocess — always available) ──
    p_norm_mean = float(np.mean(np.clip(p - _P_MIN, 0.0, None) / _P_RANGE))

    # ── count existential vars in input ──────────────────────────────────────
    try:
        e_vars = _count_existential_vars(qdimacs_path)
    except OSError:
        return 0.0
    if not e_vars:
        return 0.0
    vars_before = len(e_vars)

    # ── run preprocess, writing output to a temp file ─────────────────────────
    fd, out_path = tempfile.mkstemp(suffix=".qdimacs")
    os.close(fd)
    t_start = time.perf_counter()
    try:
        try:
            result = subprocess.run(
                [config.PREPROCESS_BIN, qdimacs_path, out_path, *_serialize_params(p)],
                capture_output=True,
                text=True,
                timeout=config.ROLLOUT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return 0.0
        except Exception:
            return 0.0
        elapsed = time.perf_counter() - t_start

        if result.returncode != 0 or not os.path.exists(out_path):
            return 0.0

        # ── count surviving existential vars ──────────────────────────────────
        try:
            surviving = e_vars & _vars_in_clauses(out_path)
        except OSError:
            return 0.0
        vars_after = len(surviving)

    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass

    # ── composite reward ──────────────────────────────────────────────────────
    r_elim  = float(vars_before - vars_after) / float(vars_before)
    t_norm  = min(elapsed / config.ROLLOUT_TIMEOUT, 1.0)
    reward  = (r_elim
               - config.TIME_PENALTY_COEFF  * t_norm
               - config.PARAM_PENALTY_COEFF * p_norm_mean)
    return reward


# ── parallel rollout ──────────────────────────────────────────────────────────

class _RolloutTask(NamedTuple):
    qdimacs_path: str
    p: np.ndarray  # shape [D]


def _run_task(task: _RolloutTask) -> float:
    return rollout(task.qdimacs_path, task.p)


def parallel_rollout(
    qdimacs_paths: list[str],
    p_batch: np.ndarray,           # [B, D]
    num_workers: int = config.NUM_WORKERS,
) -> np.ndarray:
    """Run B BVE rollouts in parallel.

    Parameters
    ----------
    qdimacs_paths : list of B QDIMACS file paths
    p_batch       : float array [B, D] in physical parameter space
    num_workers   : number of parallel worker processes

    Returns
    -------
    rewards : float array [B], each in [0, 1]
    """
    B = len(qdimacs_paths)
    tasks = [_RolloutTask(qdimacs_path=qdimacs_paths[i], p=p_batch[i]) for i in range(B)]

    if num_workers <= 1 or B == 1:
        return np.array([_run_task(t) for t in tasks], dtype=np.float32)

    with Pool(processes=min(num_workers, B)) as pool:
        rewards = pool.map(_run_task, tasks)
    return np.array(rewards, dtype=np.float32)
