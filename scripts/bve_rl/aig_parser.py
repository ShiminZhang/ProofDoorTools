"""Parse an AIGER (.aig) file into a PyTorch Geometric Data object.

Node feature layout (dim = 7):
  [0] is_AND            (one-hot node type)
  [1] is_PI             (one-hot node type)
  [2] is_PO             (one-hot node type)
  [3] is_complemented   (PO nodes: complement of driving signal; others: 0)
  [4] fanin_count_norm  (fanin_size / 2)
  [5] fanout_count_norm (fanout_size / max_fanout)
  [6] topo_level_norm   (level / max_level)

Edge layout (dim = 1):
  [0] is_complemented   (1 if the fanin signal is complement-inverted)

Edge direction: fanin → fanout  (topological PI → PO order).

PO outputs in an AIG are *signals*, not nodes.  We materialise each PO
signal as a virtual PO node, connect its driving node to it, and set
topo_level_norm = 1.0.
"""

from __future__ import annotations

import os
from typing import Dict, Tuple

import torch
from torch_geometric.data import Data


def _read_latch_count(aig_path: str) -> int:
    """Return the latch count from the AIGER header (field L)."""
    with open(aig_path, "rb") as f:
        header = f.readline().decode("ascii", errors="strict").strip()
    parts = header.split()
    if len(parts) < 6 or parts[0] not in ("aig", "aag"):
        raise ValueError(f"Not a valid AIGER file: {aig_path}")
    return int(parts[3])


def aig_to_pyg(aig_path: str) -> Data:
    """Parse *aig_path* and return a PyG Data with node/edge features."""
    from aigverse import (  # type: ignore[import-not-found]
        DepthAig,
        read_aiger_into_aig,
        read_aiger_into_sequential_aig,
    )

    nlatches = _read_latch_count(aig_path)
    raw = (
        read_aiger_into_sequential_aig(aig_path)
        if nlatches > 0
        else read_aiger_into_aig(aig_path)
    )
    depth_aig = DepthAig(raw)

    # ── Collect non-constant nodes (PI + AND gates) ──────────────────────────
    real_nodes = [n for n in raw.nodes() if not raw.is_constant(n)]
    if not real_nodes:
        # Degenerate AIG: return a minimal single-node graph
        return Data(
            x=torch.zeros(1, 7),
            edge_index=torch.zeros(2, 0, dtype=torch.long),
            edge_attr=torch.zeros(0, 1),
        )

    max_fanout = max(1, max(raw.fanout_size(n) for n in real_nodes))
    max_level  = max(1, depth_aig.num_levels())

    # Map: AIG node index → graph node index
    node_to_gidx: Dict[int, int] = {
        raw.node_to_index(n): gidx for gidx, n in enumerate(real_nodes)
    }

    # PO virtual nodes start right after real nodes
    pos        = raw.pos()
    po_start   = len(real_nodes)
    num_nodes  = po_start + len(pos)

    x = torch.zeros(num_nodes, 7)

    # ── Real-node features (PI and AND) ──────────────────────────────────────
    for gidx, n in enumerate(real_nodes):
        if raw.is_pi(n):
            x[gidx, 1] = 1.0                          # is_PI
        else:                                          # AND gate
            x[gidx, 0] = 1.0                          # is_AND
        # is_complemented stays 0 for non-PO nodes
        x[gidx, 4] = raw.fanin_size(n)  / 2.0        # fanin_count_norm
        x[gidx, 5] = raw.fanout_size(n) / max_fanout  # fanout_count_norm
        x[gidx, 6] = depth_aig.level(n) / max_level   # topo_level_norm

    # ── PO virtual-node features ──────────────────────────────────────────────
    for po_idx, sig in enumerate(pos):
        gidx = po_start + po_idx
        x[gidx, 2] = 1.0                                    # is_PO
        x[gidx, 3] = 1.0 if sig.get_complement() else 0.0  # is_complemented
        x[gidx, 4] = 0.5                                    # fanin_count_norm (1 driver / 2)
        x[gidx, 5] = 0.0                                    # fanout_count_norm
        x[gidx, 6] = 1.0                                    # topo_level_norm  (output boundary)

    # ── Build edges ───────────────────────────────────────────────────────────
    edge_src:  list[int]        = []
    edge_dst:  list[int]        = []
    edge_attr: list[list[float]] = []

    def _add_edge(src_node, dst_gidx: int, sig) -> None:
        if raw.is_constant(src_node):
            return
        src_nidx = raw.node_to_index(src_node)
        src_gidx = node_to_gidx.get(src_nidx)
        if src_gidx is None:
            return
        edge_src.append(src_gidx)
        edge_dst.append(dst_gidx)
        edge_attr.append([1.0 if sig.get_complement() else 0.0])

    # AND-gate fanin edges: signal_driver → AND_node
    for n in real_nodes:
        if not raw.is_and(n):
            continue
        dst_gidx = node_to_gidx[raw.node_to_index(n)]
        for sig in raw.fanins(n):
            _add_edge(raw.get_node(sig), dst_gidx, sig)

    # PO edges: signal_driver → virtual_PO_node
    for po_idx, sig in enumerate(pos):
        dst_gidx = po_start + po_idx
        _add_edge(raw.get_node(sig), dst_gidx, sig)

    edge_index = torch.tensor([edge_src, edge_dst], dtype=torch.long)
    edge_attr_t = (
        torch.tensor(edge_attr, dtype=torch.float)
        if edge_attr
        else torch.zeros(0, 1)
    )

    return Data(x=x, edge_index=edge_index, edge_attr=edge_attr_t)


def build_aig_cache(aig_paths: list[str]) -> dict[str, Data]:
    """Pre-parse a list of AIG files and return a path → PyG Data dict."""
    import logging
    cache: dict[str, Data] = {}
    for path in aig_paths:
        try:
            cache[path] = aig_to_pyg(path)
        except Exception as exc:
            logging.warning(f"aig_parser: skipping {path}: {exc}")
    logging.info(f"aig_parser: cached {len(cache)}/{len(aig_paths)} graphs")
    return cache
