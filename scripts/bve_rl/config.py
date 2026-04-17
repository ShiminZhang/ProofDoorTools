"""Hyperparameters and static configuration for the BVE-RL experiment."""
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

# ── Paths ──────────────────────────────────────────────────────────────────────
PREPROCESS_BIN   = os.path.join(REPO_ROOT, "External/kissat_bve/build/preprocess")
AIG_DIR          = os.path.join(REPO_ROOT, "ProofDoorBenchmark/aigs")
QDIMACS_SPD_DIR  = os.path.join(REPO_ROOT, "ProofDoorBenchmark/qdimacs_spd")

# ── BVE action space ──────────────────────────────────────────────────────────
# d parameters predicted by the policy; each has a [min, max] bound.
# tanh + affine rescale maps the raw Gaussian sample into [p_min, p_max].
PARAM_NAMES: list[str] = [
    "eliminatebound",    # max clauses added per elimination step
    "eliminaterounds",   # number of elimination rounds
    "eliminateclslim",   # max clause size during elimination
    "eliminateocclim",   # max occurrences per variable
    "eliminateeffort",   # effort budget (per-mille)
    "initialbound",      # initial additional-clauses bound for preprocess
]

PARAM_BOUNDS: list[tuple[int, int]] = [
    (1,    20_000),   # eliminatebound
    (1,     5_000),   # eliminaterounds
    (10,  500_000),   # eliminateclslim
    (10, 5_000_000),  # eliminateocclim
    (10,  200_000),   # eliminateeffort
    (1,      500),    # initialbound
]

D = len(PARAM_NAMES)  # action dimension

# ── GNN architecture ──────────────────────────────────────────────────────────
NODE_DIM       = 7    # dim of node feature vector (see aig_parser.py)
EDGE_DIM       = 1    # dim of edge feature vector (is_complemented)
HIDDEN_DIM     = 256  # GINEConv hidden width
NUM_GNN_LAYERS = 5    # number of GINEConv layers

# ── PPO hyperparameters ───────────────────────────────────────────────────────
LR              = 3e-4
CLIP_EPS        = 0.2
ENTROPY_COEFF   = 0.01   # c2 — raise if log_std collapses to −3
VALUE_COEFF     = 0.5    # c1
BATCH_SIZE      = 64     # AIGs per iteration
PPO_EPOCHS      = 4      # gradient steps per collected batch
GRAD_CLIP       = 0.5

# ── Gaussian policy ───────────────────────────────────────────────────────────
LOG_STD_INIT = 0.0   # std=1 at the start → full exploration
LOG_STD_MIN  = -3.0
LOG_STD_MAX  =  1.0

# ── Training loop ─────────────────────────────────────────────────────────────
NUM_ITERS      = 2_000
VAL_EVERY      = 10    # validate every N iterations
CKPT_EVERY     = 100   # checkpoint every N iterations

# ── Rollout ───────────────────────────────────────────────────────────────────
NUM_WORKERS      = 8    # parallel preprocess workers
ROLLOUT_TIMEOUT  = 30   # seconds per BVE call; return r=0 on timeout

# ── Reward shaping ────────────────────────────────────────────────────────────
# Composite reward:
#   r = r_elim  −  TIME_PENALTY_COEFF  · (elapsed / ROLLOUT_TIMEOUT)
#                −  PARAM_PENALTY_COEFF · mean((p_i − p_min_i) / (p_max_i − p_min_i))
#
# TIME_PENALTY_COEFF  — penalises slow runs; at max timeout costs this fraction
# PARAM_PENALTY_COEFF — penalises large parameter values; encourages parsimony
# Set either coefficient to 0.0 to disable that penalty.
TIME_PENALTY_COEFF  = 0.10   # 10 % of reward at max timeout
PARAM_PENALTY_COEFF = 0.05   # 5 % of reward when all params at upper bound
