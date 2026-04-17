"""Corpus loading and train/val/test splitting for BVE-RL.

Each corpus entry is a pair (aig_path, qdimacs_path).

QDIMACS files live at:  <QDIMACS_SPD_DIR>/<K>/<name>.<K>.<i>.qdimacs
AIG files live at:      <AIG_DIR>/<name>.aig

All (AIG, QDIMACS) pairings are included; each QDIMACS step for a given AIG
is a separate training sample.  This gives more reward signal while keeping
the policy structure (one parameter vector per AIG graph) unchanged.

Split: 80 / 10 / 10 train / val / test, stratified by AIG name so that all
QDIMACS steps from the same AIG land in the same split (avoids leakage).
"""
from __future__ import annotations

import logging
import os
import random
from typing import NamedTuple

from . import config

logger = logging.getLogger(__name__)


class CorpusEntry(NamedTuple):
    aig_path:     str
    qdimacs_path: str


# ── QDIMACS discovery ─────────────────────────────────────────────────────────

def _build_name_to_qdimacs(qdimacs_root: str) -> dict[str, list[str]]:
    """Return {name: [qdimacs_path, ...]} — all QDIMACS files per AIG name."""
    mapping: dict[str, list[str]] = {}
    if not os.path.isdir(qdimacs_root):
        logger.warning("QDIMACS root not found: %s", qdimacs_root)
        return mapping

    for k_dir in sorted(os.listdir(qdimacs_root)):
        k_path = os.path.join(qdimacs_root, k_dir)
        if not os.path.isdir(k_path):
            continue
        for fname in sorted(os.listdir(k_path)):
            if not fname.endswith(".qdimacs"):
                continue
            # Filename format: <name>.<K>.<i>.qdimacs
            stem  = fname[: -len(".qdimacs")]   # "<name>.<K>.<i>"
            parts = stem.split(".")
            if len(parts) < 3:
                continue
            name = ".".join(parts[:-2])          # strip trailing K and i
            mapping.setdefault(name, []).append(os.path.join(k_path, fname))

    return mapping


# ── corpus builder ────────────────────────────────────────────────────────────

def build_corpus(
    aig_dir:      str = config.AIG_DIR,
    qdimacs_root: str = config.QDIMACS_SPD_DIR,
) -> list[CorpusEntry]:
    """Scan AIG_DIR and pair each .aig with every matching QDIMACS file."""
    name_to_qdimacs = _build_name_to_qdimacs(qdimacs_root)

    entries: list[CorpusEntry] = []
    aig_files = sorted(f for f in os.listdir(aig_dir) if f.endswith(".aig"))

    missing_aig = 0
    for fname in aig_files:
        name     = fname[: -len(".aig")]
        aig_path = os.path.join(aig_dir, fname)
        paths    = name_to_qdimacs.get(name)
        if not paths:
            missing_aig += 1
            continue
        for qdimacs_path in paths:
            entries.append(CorpusEntry(aig_path=aig_path, qdimacs_path=qdimacs_path))

    if missing_aig:
        logger.debug("%d AIGs had no matching QDIMACS file", missing_aig)
    logger.info("Corpus: %d entries from %d AIG files", len(entries), len(aig_files) - missing_aig)
    return entries


# ── stratified split (by AIG name, not by entry) ─────────────────────────────

def split_corpus(
    entries:   list[CorpusEntry],
    val_frac:  float = 0.10,
    test_frac: float = 0.10,
    seed:      int   = 42,
) -> tuple[list[CorpusEntry], list[CorpusEntry], list[CorpusEntry]]:
    """Split corpus 80/10/10 by AIG name to prevent QDIMACS-step leakage.

    Returns (train, val, test).
    """
    if not entries:
        return [], [], []

    # Group all entries by AIG name
    by_name: dict[str, list[CorpusEntry]] = {}
    for e in entries:
        name = os.path.splitext(os.path.basename(e.aig_path))[0]
        by_name.setdefault(name, []).append(e)

    names = sorted(by_name.keys())
    rng   = random.Random(seed)
    rng.shuffle(names)

    n       = len(names)
    n_test  = max(1, round(n * test_frac))
    n_val   = max(1, round(n * val_frac))
    n_train = n - n_val - n_test

    train_names = names[:n_train]
    val_names   = names[n_train: n_train + n_val]
    test_names  = names[n_train + n_val:]

    def _collect(name_list: list[str]) -> list[CorpusEntry]:
        out: list[CorpusEntry] = []
        for nm in name_list:
            out.extend(by_name[nm])
        return out

    train = _collect(train_names)
    val   = _collect(val_names)
    test  = _collect(test_names)

    logger.info(
        "Split — train: %d  val: %d  test: %d  (AIG names: %d / %d / %d)",
        len(train), len(val), len(test),
        len(train_names), len(val_names), len(test_names),
    )
    return train, val, test
