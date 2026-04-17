"""GNN encoder + Actor-Critic for BVE parameter prediction.

Architecture (per spec):
  AIGEncoder  : GINEConv × L + GlobalAttention pooling → g ∈ R^256
  Actor       : g → Linear(256,128) → ReLU → Linear(128,d) = mean
                log_std = nn.Parameter(zeros(d))
                bound enforcement via tanh + affine rescale
  Critic      : g → Linear(256,128) → ReLU → Linear(128,1) = V(s)
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
from torch_geometric.nn import GINEConv
from torch_geometric.nn.aggr import AttentionalAggregation

from . import config


# ── helpers ──────────────────────────────────────────────────────────────────

def _mlp(dims: list[int]) -> nn.Sequential:
    layers: list[nn.Module] = []
    for i in range(len(dims) - 1):
        layers.append(nn.Linear(dims[i], dims[i + 1]))
        if i < len(dims) - 2:
            layers.append(nn.ReLU())
    return nn.Sequential(*layers)


# ── GNN Encoder ───────────────────────────────────────────────────────────────

class AIGEncoder(nn.Module):
    """GINEConv-based AIG graph encoder → graph-level embedding g ∈ R^hidden."""

    def __init__(
        self,
        node_dim: int = config.NODE_DIM,
        edge_dim: int = config.EDGE_DIM,
        hidden: int = config.HIDDEN_DIM,
        layers: int = config.NUM_GNN_LAYERS,
    ) -> None:
        super().__init__()
        # Project input node features to hidden dim before first conv
        self.node_proj = nn.Linear(node_dim, hidden)
        self.convs = nn.ModuleList([
            GINEConv(
                nn=_mlp([hidden, hidden, hidden]),
                edge_dim=edge_dim,
            )
            for _ in range(layers)
        ])
        self.pool = AttentionalAggregation(gate_nn=_mlp([hidden, 1]))

    def forward(
        self,
        x: Tensor,
        edge_index: Tensor,
        edge_attr: Tensor,
        batch: Tensor,
    ) -> Tensor:
        x = self.node_proj(x).relu()
        for conv in self.convs:
            x = conv(x, edge_index, edge_attr).relu()
        return self.pool(x, batch)  # [B, hidden]


# ── Actor ─────────────────────────────────────────────────────────────────────

class Actor(nn.Module):
    """Gaussian policy head with tanh + affine bound enforcement."""

    def __init__(
        self,
        hidden: int = config.HIDDEN_DIM,
        action_dim: int = config.D,
    ) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(hidden, 128),
            nn.ReLU(),
            nn.Linear(128, action_dim),
        )
        self.log_std = nn.Parameter(
            torch.full((action_dim,), config.LOG_STD_INIT)
        )
        # Register bounds as buffers (not optimised)
        p_min = torch.tensor([b[0] for b in config.PARAM_BOUNDS], dtype=torch.float)
        p_max = torch.tensor([b[1] for b in config.PARAM_BOUNDS], dtype=torch.float)
        self.register_buffer("p_min", p_min)
        self.register_buffer("p_max", p_max)

    # ── internal helpers ──────────────────────────────────────────────────────

    def _std(self) -> Tensor:
        return self.log_std.clamp(config.LOG_STD_MIN, config.LOG_STD_MAX).exp()

    def _rescale(self, p_raw: Tensor) -> Tensor:
        """Map unconstrained sample → [p_min, p_max] via tanh affine rescale."""
        return self.p_min + (self.p_max - self.p_min) * 0.5 * (p_raw.tanh() + 1.0)

    def _log_prob(self, mean: Tensor, std: Tensor, p_raw: Tensor) -> Tensor:
        """Log-probability of *p_raw* under N(mean, std²).

        Because we apply a tanh transform we need the change-of-variables
        correction:  log π(p) = log N(p_raw | mean, std) - log|d(tanh)/dp_raw|
                               = log N(p_raw | mean, std) - sum log(1 - tanh²)
        """
        normal = torch.distributions.Normal(mean, std)
        log_p = normal.log_prob(p_raw)                       # [B, d]
        # tanh squash correction
        log_p = log_p - torch.log1p(-p_raw.tanh().pow(2) + 1e-6)
        return log_p.sum(dim=-1)                             # [B]

    # ── public API ────────────────────────────────────────────────────────────

    def forward(self, g: Tensor) -> tuple[Tensor, Tensor]:
        """Return (mean, std) of the Gaussian policy."""
        mean = self.net(g)
        std  = self._std().expand_as(mean)
        return mean, std

    def sample(self, g: Tensor) -> tuple[Tensor, Tensor]:
        """Sample action p and return (p_bounded, log_prob)."""
        mean, std = self.forward(g)
        dist   = torch.distributions.Normal(mean, std)
        p_raw  = dist.rsample()                     # reparametrised sample
        p      = self._rescale(p_raw)               # bounded action
        log_p  = self._log_prob(mean, std, p_raw)
        return p, log_p

    def log_prob(self, g: Tensor, p_raw: Tensor) -> Tensor:
        """Evaluate log π(p_raw | g) — used during PPO update."""
        mean, std = self.forward(g)
        return self._log_prob(mean, std, p_raw)

    def entropy(self, g: Tensor) -> Tensor:
        """Approximate entropy: H[N(mean,std)] (before tanh transform)."""
        _, std = self.forward(g)
        return torch.distributions.Normal(torch.zeros_like(std), std).entropy().sum(dim=-1)


# ── Critic ────────────────────────────────────────────────────────────────────

class Critic(nn.Module):
    """Scalar state-value head V(s)."""

    def __init__(self, hidden: int = config.HIDDEN_DIM) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(hidden, 128),
            nn.ReLU(),
            nn.Linear(128, 1),
        )

    def forward(self, g: Tensor) -> Tensor:
        return self.net(g).squeeze(-1)  # [B]


# ── Combined model ─────────────────────────────────────────────────────────────

class BVEPolicy(nn.Module):
    """Full encoder + actor + critic."""

    def __init__(self) -> None:
        super().__init__()
        self.encoder = AIGEncoder()
        self.actor   = Actor()
        self.critic  = Critic()

    def encode(self, x, edge_index, edge_attr, batch) -> Tensor:
        return self.encoder(x, edge_index, edge_attr, batch)

    def act(self, g: Tensor) -> tuple[Tensor, Tensor, Tensor, Tensor]:
        """Return (p_bounded, p_raw, log_prob, value)."""
        mean, std = self.actor.forward(g)
        dist   = torch.distributions.Normal(mean, std)
        p_raw  = dist.rsample()
        p      = self.actor._rescale(p_raw)
        log_p  = self.actor._log_prob(mean, std, p_raw)
        v      = self.critic(g)
        return p, p_raw, log_p, v

    def evaluate(self, g: Tensor, p_raw: Tensor) -> tuple[Tensor, Tensor, Tensor]:
        """Return (log_prob, entropy, value) for stored (g, p_raw)."""
        log_p = self.actor.log_prob(g, p_raw)
        ent   = self.actor.entropy(g)
        v     = self.critic(g)
        return log_p, ent, v

    def greedy_params(self, g: Tensor) -> Tensor:
        """Return deterministic (mean) rescaled parameters — for inference."""
        mean_raw = self.actor.net(g)
        return self.actor._rescale(mean_raw)
