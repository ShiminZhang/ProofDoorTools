#!/usr/bin/env python3
"""
SPD Complexity Analysis
=======================
Analyzes the relationship between the linear/exponential proof-door tag and
the observed growth behaviour of the Strongest Proof-Door (SPD) interpolant.

Usage (run from repo root):
    python scripts/spd_analysis.py [--out_dir figures/spd_analysis]

Outputs
-------
  spd_analysis_data.csv          – per-(instance,K) summary table
  spd_growth_classified.csv      – growth label for every classifiable instance
  figures:
    01_infeasibility_rates.pdf   – stacked-bar: none/partial/complete by category × K
    02_spd_trajectories_k5.pdf   – SPD-size trajectories coloured by tag
    03_max_spd_distribution.pdf  – box + strip plot of max SPD size by category
    04_growth_confusion.pdf      – confusion matrix: tag vs SPD-growth class
    05_spd_vs_tag_scatter.pdf    – scatter log max-SPD vs log PD-size, coloured by tag
  spd_analysis_report.txt        – statistical test results (Fisher, Mann-Whitney, …)
"""

import argparse
import csv
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# ── optional heavy imports (gracefully degrade) ──────────────────────────────
try:
    import numpy as np
    HAVE_NP = True
except ImportError:
    HAVE_NP = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    HAVE_MPL = True
except ImportError:
    HAVE_MPL = False

try:
    from scipy import stats as sp_stats
    HAVE_SP = True
except ImportError:
    HAVE_SP = False

# ── paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT    = Path(__file__).parent.parent
INTERP_BASE  = REPO_ROOT / "ProofDoorBenchmark" / "interpolants_def5"
LINEAR_CSV   = REPO_ROOT / "linear.csv"
EXPONENTIAL_CSV = REPO_ROOT / "exponential.csv"

# ── constants ─────────────────────────────────────────────────────────────────
# Growth classification thresholds
GROWTH_RATIO_EXP_THRESHOLD  = 10.0   # max/min > 10 → candidate for exponential
GROWTH_LOG_SLOPE_EXP_MIN    = 0.3    # slope of log(size) vs i > 0.3 → exponential
GROWTH_RATIO_CONST_THRESHOLD = 2.0   # max/min < 2 → constant

COLOR_LIN = "#2196F3"   # blue  – linear tag
COLOR_EXP = "#F44336"   # red   – exponential tag


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────

def load_tags():
    """Return (lin_set, exp_set) of instance names."""
    lin = {r["instance_name"] for r in csv.DictReader(open(LINEAR_CSV))}
    exp = {r["instance_name"] for r in csv.DictReader(open(EXPONENTIAL_CSV))}
    return lin, exp


def read_num_clauses(path: Path) -> int | None:
    """Parse the number of clauses from a QDIMACS/DIMACS header."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("p cnf"):
                    return int(line.split()[3])
    except Exception:
        pass
    return None


def load_spd_records() -> dict:
    """
    Returns records[(name, K)] = dict{iter_idx: num_clauses}
    scanning all K sub-dirs of INTERP_BASE.
    """
    records = {}
    if not INTERP_BASE.exists():
        print(f"[WARN] interpolants dir not found: {INTERP_BASE}", file=sys.stderr)
        return records

    for k_str in sorted(os.listdir(INTERP_BASE)):
        try:
            K = int(k_str)
        except ValueError:
            continue
        k_dir = INTERP_BASE / k_str
        per_inst: dict[str, dict[int, int]] = defaultdict(dict)

        for fname in os.listdir(k_dir):
            m = re.match(r"^(.+)\.(\d+)\.(\d+)\.interpolant$", fname)
            if not m:
                continue
            name, fk, i = m.group(1), int(m.group(2)), int(m.group(3))
            if fk != K:
                continue
            nc = read_num_clauses(k_dir / fname)
            if nc is not None:
                per_inst[name][i] = nc

        for name, iters in per_inst.items():
            records[(name, K)] = dict(iters)

    return records


# ─────────────────────────────────────────────────────────────────────────────
# Per-instance statistics
# ─────────────────────────────────────────────────────────────────────────────

def completeness_label(name: str, K: int, iters: dict) -> str:
    if not iters:
        return "none"
    if sorted(iters.keys()) == list(range(K)):
        return "complete"
    return "partial"


def classify_growth(iters: dict) -> str:
    """
    Classify the SPD-size growth pattern from available iteration data.
    Returns one of: 'constant', 'exponential', 'non-monotone', 'insufficient'.
    """
    if len(iters) < 2:
        return "insufficient"

    seq = [iters[i] for i in sorted(iters.keys())]
    mn, mx = min(seq), max(seq)
    if mn == 0:
        return "insufficient"
    ratio = mx / mn

    if ratio < GROWTH_RATIO_CONST_THRESHOLD:
        return "constant"

    # Fit log(size) ~ slope * step_index to assess growth rate
    if HAVE_NP:
        xs = list(range(len(seq)))
        ys_log = [math.log(max(v, 1)) for v in seq]
        # simple OLS slope
        n = len(xs)
        sx = sum(xs); sy = sum(ys_log)
        sxy = sum(x * y for x, y in zip(xs, ys_log))
        sxx = sum(x * x for x in xs)
        denom = n * sxx - sx * sx
        slope = (n * sxy - sx * sy) / denom if denom != 0 else 0.0
    else:
        # Fallback: slope between first and last
        slope = (math.log(max(seq[-1], 1)) - math.log(max(seq[0], 1))) / max(len(seq) - 1, 1)

    if slope >= GROWTH_LOG_SLOPE_EXP_MIN and ratio >= GROWTH_RATIO_EXP_THRESHOLD:
        return "exponential"
    elif slope < 0 and ratio >= GROWTH_RATIO_EXP_THRESHOLD:
        return "non-monotone"
    else:
        return "sub-exponential"


def build_summary(records: dict, lin_set: set, exp_set: set) -> list[dict]:
    """
    Build a flat per-(instance,K) summary, but ONLY for (instance,K) pairs
    where SPD computation was actually attempted.

    "Attempted" = the instance appears in records for that K (it has at least
    one interpolant file, possibly zero clauses) OR has zero steps due to
    immediate failure.  We derive this from the records dict: if a key
    (name, K) is absent, the computation was simply never run for that K.
    """
    rows = []
    for (name, K), iters in records.items():
        tag = ("linear" if name in lin_set
               else "exponential" if name in exp_set
               else "unknown")
        comp       = completeness_label(name, K, iters)
        n_computed = len(iters)
        max_size   = max(iters.values()) if iters else None
        min_size   = min(iters.values()) if iters else None
        last_size  = iters.get(max(iters.keys())) if iters else None
        growth     = (classify_growth(iters) if n_computed >= 2
                      else ("none" if not iters else "insufficient"))
        peak_ratio = ((max_size / min_size)
                      if (max_size and min_size and min_size > 0) else None)

        rows.append({
            "instance":     name,
            "K":            K,
            "tag":          tag,
            "completeness": comp,
            "n_computed":   n_computed,
            "max_spd":      max_size,
            "min_spd":      min_size,
            "last_spd":     last_size,
            "peak_ratio":   peak_ratio,
            "growth_class": growth,
        })

    return rows


def build_natural_K_map(lin_csv: Path, exp_csv: Path) -> dict[str, int]:
    """
    Returns {instance_name: natural_K} where natural_K is the K listed
    in the CSV file (the K at which the instance was classified).
    Linear instances all have K=10; exponential vary.
    """
    nk = {}
    for row in csv.DictReader(open(lin_csv)):
        nk[row["instance_name"]] = int(row["K"])
    for row in csv.DictReader(open(exp_csv)):
        nk[row["instance_name"]] = int(row["K"])
    return nk


# ─────────────────────────────────────────────────────────────────────────────
# Statistical tests
# ─────────────────────────────────────────────────────────────────────────────

def fisher_exact_2x2(a, b, c, d):
    """
    Simple Fisher's exact test for the 2×2 table:
        [a  b]
        [c  d]
    Returns (odds_ratio, p_value).
    Uses scipy if available, otherwise computes exact p via hypergeometric sum.
    """
    if HAVE_SP:
        odds, p = sp_stats.fisher_exact([[a, b], [c, d]])
        return float(odds), float(p)
    # Minimal exact computation via hypergeometric CDF
    import math
    n = a + b + c + d
    r1 = a + b; r2 = c + d; c1 = a + c; c2 = b + d
    def log_comb(n, k):
        if k < 0 or k > n: return -math.inf
        return math.lgamma(n+1) - math.lgamma(k+1) - math.lgamma(n-k+1)
    def log_hyper(k, n, K, N):
        return log_comb(K,k) + log_comb(N-K, n-k) - log_comb(N, n)
    lo = max(0, r1 - c2); hi = min(r1, c1)
    log_p_obs = log_hyper(a, r1, c1, n)
    log_probs = [log_hyper(k, r1, c1, n) for k in range(lo, hi+1)]
    p_obs = math.exp(log_p_obs)
    total_prob = sum(math.exp(lp) for lp in log_probs)
    p_val = sum(math.exp(lp) for lp in log_probs if math.exp(lp) <= p_obs + 1e-10)
    p_val = min(p_val / total_prob, 1.0) if total_prob > 0 else 1.0
    odds = (a * d) / (b * c) if (b * c) > 0 else float("inf")
    return odds, p_val


def mann_whitney(group_a, group_b):
    """Returns (U statistic, p_value) for a two-sided MWU test."""
    if HAVE_SP and group_a and group_b:
        res = sp_stats.mannwhitneyu(group_a, group_b, alternative="two-sided")
        return float(res.statistic), float(res.pvalue)
    # Fallback: just return U and nan
    na, nb = len(group_a), len(group_b)
    u = 0
    for a in group_a:
        for b in group_b:
            if a > b: u += 1
            elif a == b: u += 0.5
    return u, float("nan")


# ─────────────────────────────────────────────────────────────────────────────
# Plotting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _save(fig, out_dir: Path, filename: str):
    path = out_dir / filename
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"  saved → {path}")


def plot_infeasibility_rates(summary: list[dict], out_dir: Path, Ks=(5, 10)):
    """
    Stacked bar: none / partial / complete by tag × K.
    Only instances that were ACTUALLY ATTEMPTED (present in summary) are shown.
    """
    if not HAVE_MPL:
        return

    Ks = [K for K in Ks if any(r["K"] == K for r in summary)]
    if not Ks:
        return

    fig, axes = plt.subplots(1, len(Ks), figsize=(4 * len(Ks) + 1, 4.5), sharey=False)
    if len(Ks) == 1:
        axes = [axes]

    for ax, K in zip(axes, Ks):
        rows = [r for r in summary if r["K"] == K
                and r["tag"] in ("linear", "exponential")]
        if not rows:
            ax.set_title(f"K={K} (no data)")
            continue

        cats = ["linear", "exponential"]
        comp_cnts = {c: defaultdict(int) for c in cats}
        for r in rows:
            comp_cnts[r["tag"]][r["completeness"]] += 1

        cats_present = [c for c in cats if sum(comp_cnts[c].values()) > 0]
        labels = ["complete", "partial", "none"]
        colors = ["#4CAF50", "#FF9800", "#EF5350"]

        x = range(len(cats_present))
        bottoms = [0] * len(cats_present)
        for label, color in zip(labels, colors):
            vals = [comp_cnts[cat][label] for cat in cats_present]
            ax.bar(x, vals, bottom=bottoms, color=color, label=label, alpha=0.85, width=0.5)
            bottoms = [b + v for b, v in zip(bottoms, vals)]

        totals = [sum(comp_cnts[c].values()) for c in cats_present]
        for xi, (cat, tot) in enumerate(zip(cats_present, totals)):
            nc = comp_cnts[cat]["none"]
            if tot > 0:
                ax.text(xi, tot + 0.5,
                        f"fail: {nc}/{tot}\n({100*nc/tot:.0f}%)",
                        ha="center", va="bottom", fontsize=8)

        ax.set_xticks(list(x))
        ax.set_xticklabels(cats_present)
        ax.set_ylabel("Attempted instances")
        ax.set_title(f"SPD status among attempted  (K={K})")
        if K == Ks[0]:
            ax.legend(title="result", fontsize=8)

    fig.tight_layout()
    _save(fig, out_dir, "01_infeasibility_rates.pdf")


def plot_trajectories(records: dict, lin_set: set, exp_set: set, out_dir: Path, K=5,
                      max_lin=60, max_exp=60):
    """SPD-size trajectories over iteration index, coloured by tag."""
    if not HAVE_MPL:
        return

    fig, ax = plt.subplots(figsize=(9, 5))

    def _plot_group(instance_set, color, label, alpha=0.35, lw=0.8, max_n=60):
        plotted = 0
        for name in sorted(instance_set):
            iters = records.get((name, K), {})
            if len(iters) < 2:
                continue
            xs = sorted(iters.keys())
            ys = [iters[i] for i in xs]
            ax.plot(xs, ys, color=color, alpha=alpha, lw=lw)
            plotted += 1
            if plotted >= max_n:
                break

    _plot_group(exp_set, COLOR_EXP, "exponential", max_n=max_exp)
    _plot_group(lin_set, COLOR_LIN, "linear",      max_n=max_lin)

    ax.set_yscale("log")
    ax.set_xlabel("SPD step index  i")
    ax.set_ylabel("SPD size (number of clauses)  [log scale]")
    ax.set_title(f"SPD interpolant size trajectories  (K={K})")
    ax.legend(handles=[
        mpatches.Patch(color=COLOR_LIN, label="linear-tagged"),
        mpatches.Patch(color=COLOR_EXP, label="exponential-tagged"),
    ])
    fig.tight_layout()
    _save(fig, out_dir, f"02_spd_trajectories_k{K}.pdf")


def plot_max_spd_distribution(summary: list[dict], out_dir: Path, K=5):
    """Box + strip plot of max SPD size by category."""
    if not HAVE_MPL:
        return

    rows = [r for r in summary if r["K"] == K and r["max_spd"] is not None]
    lin_vals = [math.log10(r["max_spd"]) for r in rows if r["tag"] == "linear"  and r["max_spd"] > 0]
    exp_vals = [math.log10(r["max_spd"]) for r in rows if r["tag"] == "exponential" and r["max_spd"] > 0]

    if not lin_vals and not exp_vals:
        return

    fig, ax = plt.subplots(figsize=(6, 5))

    data   = [lin_vals, exp_vals]
    colors = [COLOR_LIN, COLOR_EXP]
    labels = ["linear-tagged", "exponential-tagged"]
    positions = [1, 2]

    bp = ax.boxplot(data, positions=positions, patch_artist=True,
                    widths=0.5, showfliers=False,
                    medianprops=dict(color="black", lw=2))
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.55)

    import random
    random.seed(42)
    for pos, vals, color in zip(positions, data, colors):
        jitter = [pos + random.uniform(-0.18, 0.18) for _ in vals]
        ax.scatter(jitter, vals, color=color, alpha=0.4, s=18, zorder=3)

    ax.set_xticks(positions)
    ax.set_xticklabels(labels)
    ax.set_ylabel("log₁₀(max SPD size in clauses)")
    ax.set_title(f"Max SPD size distribution by tag  (K={K}, n_lin={len(lin_vals)}, n_exp={len(exp_vals)})")
    fig.tight_layout()
    _save(fig, out_dir, f"03_max_spd_distribution_k{K}.pdf")


def plot_growth_confusion(summary: list[dict], out_dir: Path, K=5):
    """Heatmap: tag (rows) × SPD growth class (columns)."""
    if not HAVE_MPL:
        return

    rows = [r for r in summary if r["K"] == K and r["growth_class"] not in ("none", "insufficient")]
    tags   = ["linear", "exponential"]
    growth = ["constant", "sub-exponential", "non-monotone", "exponential"]

    mat = [[0]*len(growth) for _ in tags]
    for r in rows:
        ti = tags.index(r["tag"]) if r["tag"] in tags else -1
        gi = growth.index(r["growth_class"]) if r["growth_class"] in growth else -1
        if ti >= 0 and gi >= 0:
            mat[ti][gi] += 1

    fig, ax = plt.subplots(figsize=(7, 3.5))
    im = ax.imshow([[v for v in row] for row in mat], cmap="Blues", aspect="auto")

    ax.set_xticks(range(len(growth)))
    ax.set_xticklabels(growth, rotation=30, ha="right")
    ax.set_yticks(range(len(tags)))
    ax.set_yticklabels(tags)
    ax.set_xlabel("SPD growth class")
    ax.set_ylabel("Instance tag")
    ax.set_title(f"Tag vs SPD growth class  (K={K})")

    for i in range(len(tags)):
        for j in range(len(growth)):
            ax.text(j, i, str(mat[i][j]), ha="center", va="center",
                    color="white" if mat[i][j] > max(max(row) for row in mat) * 0.6 else "black",
                    fontsize=12, fontweight="bold")

    fig.colorbar(im, ax=ax, label="count")
    fig.tight_layout()
    _save(fig, out_dir, f"04_growth_confusion_k{K}.pdf")


def plot_scatter_max_spd(summary: list[dict], out_dir: Path, K=5):
    """Scatter: log max_spd vs instance (sorted), coloured by tag and growth class."""
    if not HAVE_MPL:
        return

    rows = sorted(
        [r for r in summary if r["K"] == K and r["max_spd"] is not None and r["max_spd"] > 0],
        key=lambda r: (r["tag"], r["max_spd"])
    )
    if not rows:
        return

    lin_rows = [r for r in rows if r["tag"] == "linear"]
    exp_rows = [r for r in rows if r["tag"] == "exponential"]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4), sharey=True)

    for ax, group, color, title in [
        (axes[0], lin_rows, COLOR_LIN, "Linear-tagged"),
        (axes[1], exp_rows, COLOR_EXP, "Exponential-tagged"),
    ]:
        if not group:
            ax.set_title(title + " (no data)")
            continue
        xs = range(len(group))
        ys = [math.log10(r["max_spd"]) for r in group]
        # colour by growth class
        gc_colors = {
            "constant":        "#4CAF50",
            "sub-exponential": "#FF9800",
            "non-monotone":    "#9C27B0",
            "exponential":     "#F44336",
            "insufficient":    "#9E9E9E",
            "none":            "#9E9E9E",
        }
        point_colors = [gc_colors.get(r["growth_class"], "#9E9E9E") for r in group]
        ax.scatter(xs, ys, c=point_colors, s=22, alpha=0.8)
        ax.set_xlabel("Instance rank (sorted by max SPD)")
        ax.set_ylabel("log₁₀(max SPD size)" if ax == axes[0] else "")
        ax.set_title(f"{title}  (n={len(group)})")

    # Shared legend for growth classes
    gc_legend = [
        mpatches.Patch(color="#4CAF50", label="constant"),
        mpatches.Patch(color="#FF9800", label="sub-exponential"),
        mpatches.Patch(color="#9C27B0", label="non-monotone"),
        mpatches.Patch(color="#F44336", label="exponential"),
        mpatches.Patch(color="#9E9E9E", label="insufficient/none"),
    ]
    axes[1].legend(handles=gc_legend, title="SPD growth class",
                   loc="upper left", fontsize=8)

    fig.suptitle(f"Max SPD size by instance, coloured by growth class  (K={K})")
    fig.tight_layout()
    _save(fig, out_dir, f"05_max_spd_scatter_k{K}.pdf")


def plot_infeasibility_by_K(records: dict, lin_set: set, exp_set: set, out_dir: Path):
    """For each K with both categories present, show infeasibility rate."""
    if not HAVE_MPL:
        return

    Ks = sorted({K for (_, K) in records.keys()})
    lin_infeas_rates, exp_infeas_rates, Ks_both = [], [], []

    for K in Ks:
        lin_inst = [n for n in lin_set if (n, K) in records or True]
        exp_inst = [n for n in exp_set if (n, K) in records or True]
        # count total known instances at this K (from csv or records)
        lin_total  = len([n for n in lin_set])   # all lin instances
        exp_total  = len([n for n in exp_set])
        lin_with   = sum(1 for n in lin_set if records.get((n, K)))
        exp_with   = sum(1 for n in exp_set if records.get((n, K)))
        if lin_with == 0 and exp_with == 0:
            continue
        lin_infeas_rates.append(1.0 - lin_with / lin_total)
        exp_infeas_rates.append(1.0 - exp_with / exp_total)
        Ks_both.append(K)

    if not Ks_both:
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(Ks_both, [r * 100 for r in lin_infeas_rates], "o-", color=COLOR_LIN,
            label="linear-tagged", lw=2)
    ax.plot(Ks_both, [r * 100 for r in exp_infeas_rates], "s-", color=COLOR_EXP,
            label="exponential-tagged", lw=2)
    ax.set_xlabel("K (proof door depth)")
    ax.set_ylabel("Infeasibility rate  (%)")
    ax.set_title("SPD infeasibility rate vs K by tag")
    ax.legend()
    ax.set_ylim(0, 105)
    ax.axhline(100, color="gray", ls="--", lw=0.8)
    fig.tight_layout()
    _save(fig, out_dir, "06_infeasibility_by_K.pdf")


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────

def write_report(summary: list[dict], records: dict, lin_set: set, exp_set: set,
                 nat_K: dict, report_path: Path):
    """
    summary only contains (instance,K) pairs that were ACTUALLY ATTEMPTED.
    nat_K maps instance_name → natural K from the CSV.
    """
    lines = []
    lines.append("=" * 70)
    lines.append("SPD COMPLEXITY ANALYSIS  –  Statistical Report")
    lines.append("(Only instances where SPD computation was attempted are counted.)")
    lines.append("=" * 70)

    # ── Section 1: K=5 (most balanced dataset) ───────────────────────────────
    for focus_K in sorted({r["K"] for r in summary}):
        rows_K = [r for r in summary if r["K"] == focus_K
                  and r["tag"] in ("linear", "exponential")]
        lin_rows = [r for r in rows_K if r["tag"] == "linear"]
        exp_rows = [r for r in rows_K if r["tag"] == "exponential"]
        if not lin_rows and not exp_rows:
            continue
        if len(lin_rows) + len(exp_rows) < 5:
            continue  # skip near-empty K values

        lines.append(f"\n{'─'*60}")
        lines.append(f"K = {focus_K}  (SPD computation was attempted for both categories)")
        lines.append(f"  linear attempted: {len(lin_rows)}  |  exponential attempted: {len(exp_rows)}")
        lines.append(f"{'─'*60}")

        def comp_counts(grp):
            d = defaultdict(int)
            for r in grp:
                d[r["completeness"]] += 1
            return d

        lc = comp_counts(lin_rows); lt = len(lin_rows)
        ec = comp_counts(exp_rows); et = len(exp_rows)

        lines.append(f"\n[Completeness among attempted instances]")
        lines.append(f"{'':20s} {'linear':>12s}  {'exponential':>12s}")
        for s in ["complete", "partial", "none"]:
            lp = 100*lc[s]/lt if lt else 0
            ep = 100*ec[s]/et if et else 0
            lines.append(f"  {s:18s} {lc[s]:5d} ({lp:5.1f}%)  {ec[s]:5d} ({ep:5.1f}%)")

        # Fisher: first-step failure ("none") vs any data
        lin_none = lc["none"]; lin_ok = lt - lin_none
        exp_none = ec["none"]; exp_ok = et - exp_none
        if lt > 0 and et > 0 and (lin_none + exp_none) > 0:
            odds, pval = fisher_exact_2x2(lin_ok, lin_none, exp_ok, exp_none)
            lines.append(f"\n[Fisher's exact – first-step failure (no SPD at all)]")
            lines.append(f"  Table: lin=[[ok={lin_ok}, none={lin_none}]]  exp=[[ok={exp_ok}, none={exp_none}]]")
            lines.append(f"  Odds ratio = {odds:.3f},  p = {pval:.4g}")
            _sig = ("***" if pval<0.001 else ("*" if pval<0.05 else "n.s."))
            lines.append(f"  → {_sig}")

        # Fisher: incomplete (partial+none) vs complete
        lin_inc = lc["partial"] + lc["none"]; lin_done = lc["complete"]
        exp_inc = ec["partial"] + ec["none"]; exp_done = ec["complete"]
        if lt > 0 and et > 0:
            odds2, pval2 = fisher_exact_2x2(lin_done, lin_inc, exp_done, exp_inc)
            lines.append(f"\n[Fisher's exact – complete vs incomplete]")
            lines.append(f"  Table: lin=[[done={lin_done}, inc={lin_inc}]]  exp=[[done={exp_done}, inc={exp_inc}]]")
            lines.append(f"  OR = {odds2:.3f},  p = {pval2:.4g}")
            _sig2 = ("***" if pval2<0.001 else ("*" if pval2<0.05 else "n.s."))
            lines.append(f"  → {_sig2}")

        # Mann-Whitney on max_spd
        lin_max = [r["max_spd"] for r in lin_rows if r["max_spd"] is not None]
        exp_max = [r["max_spd"] for r in exp_rows if r["max_spd"] is not None]
        if lin_max and exp_max:
            U, p_mw = mann_whitney(lin_max, exp_max)
            med_l = sorted(lin_max)[len(lin_max)//2]
            med_e = sorted(exp_max)[len(exp_max)//2]
            mean_l = sum(lin_max)/len(lin_max)
            mean_e = sum(exp_max)/len(exp_max)
            lines.append(f"\n[Mann-Whitney U – max SPD size (clauses)]")
            lines.append(f"  linear   n={len(lin_max)}  median={med_l}  mean={mean_l:.0f}")
            lines.append(f"  expon.   n={len(exp_max)}  median={med_e}  mean={mean_e:.0f}")
            lines.append(f"  U={U:.1f},  p={p_mw:.4g}")
            _sig3 = ("***" if (not math.isnan(p_mw) and p_mw<0.001) else
                     ("*"   if (not math.isnan(p_mw) and p_mw<0.05)  else "n.s. / see scipy"))
            lines.append(f"  → {_sig3}")
            if lin_max and exp_max and med_l > 0:
                lines.append(f"  Fold difference (median): {med_e/med_l:.1f}×")

        # Growth classification
        gc_rows = [r for r in rows_K if r["growth_class"] not in ("none", "insufficient")]
        if gc_rows:
            growth_classes = ["constant", "sub-exponential", "non-monotone", "exponential"]
            gc_lin = defaultdict(int); gc_exp = defaultdict(int)
            for r in gc_rows:
                if r["tag"] == "linear":      gc_lin[r["growth_class"]] += 1
                if r["tag"] == "exponential": gc_exp[r["growth_class"]] += 1
            lt_gc = sum(gc_lin.values()); et_gc = sum(gc_exp.values())
            lines.append(f"\n[SPD Growth classification  (instances with ≥2 steps)]")
            lines.append(f"  {'growth_class':20s} {'linear':>8s}  {'%':>6s}  {'expon.':>8s}  {'%':>6s}")
            for g in growth_classes:
                lp = 100*gc_lin[g]/lt_gc if lt_gc else 0
                ep = 100*gc_exp[g]/et_gc if et_gc else 0
                lines.append(f"  {g:20s} {gc_lin[g]:8d}  {lp:5.1f}%  {gc_exp[g]:8d}  {ep:5.1f}%")
            lines.append(f"  {'total':20s} {lt_gc:8d}          {et_gc:8d}")

            a = gc_lin["exponential"]
            b = sum(gc_lin[g] for g in growth_classes if g != "exponential")
            c = gc_exp["exponential"]
            d = sum(gc_exp[g] for g in growth_classes if g != "exponential")
            if (a+b) > 0 and (c+d) > 0:
                odds3, pval3 = fisher_exact_2x2(a, b, c, d)
                lines.append(f"\n  Fisher's exact (exponential-growth vs rest):")
                lines.append(f"    lin=[[exp={a}, rest={b}]]  exp=[[exp={c}, rest={d}]]")
                lines.append(f"    OR={odds3:.3f},  p={pval3:.4g}")
                _sig4 = ("***" if pval3<0.001 else ("*" if pval3<0.05 else "n.s."))
                lines.append(f"    → {_sig4}")

        # Sensitivity: how robust is the growth finding under label noise?
        gc_rows2 = [r for r in rows_K if r["growth_class"] not in ("none","insufficient")
                    and r["tag"] in ("linear","exponential")]
        if gc_rows2:
            gc_lin2 = defaultdict(int); gc_exp2 = defaultdict(int)
            for r in gc_rows2:
                if r["tag"] == "linear":      gc_lin2[r["growth_class"]] += 1
                if r["tag"] == "exponential": gc_exp2[r["growth_class"]] += 1
            a0 = gc_lin2["exponential"]
            b0 = sum(gc_lin2[g] for g in ["constant","sub-exponential","non-monotone"])
            c0 = gc_exp2["exponential"]
            d0 = sum(gc_exp2[g] for g in ["constant","sub-exponential","non-monotone"])
            lines.append(f"\n  [Sensitivity – label noise on growth finding]")
            for flip_pct in (0, 10, 20):
                # worst-case flip: move exponential-growing exp→lin and non-exp lin→exp
                fn_e = min(int((c0+d0)*flip_pct/100), c0)
                fn_l = min(int((a0+b0)*flip_pct/100), b0)
                a_ = max(0, a0+fn_e); b_ = max(0, b0-fn_l)
                c_ = max(0, c0-fn_e); d_ = max(0, d0+fn_l)
                if (a_+b_) > 0 and (c_+d_) > 0:
                    _, pv = fisher_exact_2x2(a_, b_, c_, d_)
                    lines.append(f"    worst-case {flip_pct:2d}% label noise → p = {pv:.4g}")

    # ── Section 2: Natural-K view ─────────────────────────────────────────────
    lines.append(f"\n{'═'*60}")
    lines.append("AT NATURAL K  (each instance evaluated at the K in its CSV row)")
    lines.append(f"{'═'*60}")

    lin_natural = []
    exp_natural = []
    for (name, K), iters in records.items():
        if nat_K.get(name) != K:
            continue
        tag = "linear" if name in lin_set else "exponential" if name in exp_set else None
        if tag is None:
            continue
        comp = completeness_label(name, K, iters)
        max_sz = max(iters.values()) if iters else None
        gc = classify_growth(iters) if len(iters) >= 2 else ("none" if not iters else "insufficient")
        entry = {"name": name, "K": K, "comp": comp, "max_spd": max_sz, "gc": gc}
        if tag == "linear":      lin_natural.append(entry)
        if tag == "exponential": exp_natural.append(entry)

    def _stat_block(grp, name):
        comp_c = defaultdict(int)
        for e in grp: comp_c[e["comp"]] += 1
        gc_c   = defaultdict(int)
        for e in grp:
            if e["gc"] not in ("none","insufficient"): gc_c[e["gc"]] += 1
        lines.append(f"\n{name}  (n={len(grp)}, natural K values used):")
        for s in ["complete","partial","none"]:
            pct = 100*comp_c[s]/len(grp) if grp else 0
            lines.append(f"  {s:12s}: {comp_c[s]:4d} ({pct:5.1f}%)")
        lines.append(f"  Growth classes (among ≥2-step instances):")
        gc_total = sum(gc_c.values())
        for g in ["constant","sub-exponential","non-monotone","exponential"]:
            pct = 100*gc_c[g]/gc_total if gc_total else 0
            lines.append(f"    {g:20s}: {gc_c[g]:4d} ({pct:5.1f}%)")
        maxs = [e["max_spd"] for e in grp if e["max_spd"]]
        if maxs:
            med = sorted(maxs)[len(maxs)//2]
            lines.append(f"  Median max SPD: {med}")
        return comp_c, gc_c

    lc_nat, lgc_nat = _stat_block(lin_natural, "Linear instances at K=10")
    ec_nat, egc_nat = _stat_block(exp_natural, "Exponential instances at their natural K")

    if lin_natural and exp_natural:
        ln = len(lin_natural); en = len(exp_natural)
        l_none = lc_nat["none"]; e_none = ec_nat["none"]
        odds_n, pval_n = fisher_exact_2x2(ln-l_none, l_none, en-e_none, e_none)
        lines.append(f"\n  Fisher (first-step failure at natural K): OR={odds_n:.3f} p={pval_n:.4g}")

        a = lgc_nat["exponential"]; b = sum(lgc_nat[g] for g in ["constant","sub-exponential","non-monotone"])
        c = egc_nat["exponential"]; d = sum(egc_nat[g] for g in ["constant","sub-exponential","non-monotone"])
        if (a+b)>0 and (c+d)>0:
            odds_g, pval_g = fisher_exact_2x2(a, b, c, d)
            lines.append(f"  Fisher (exp-growth at natural K): OR={odds_g:.3f} p={pval_g:.4g}")

        lin_max_n = [e["max_spd"] for e in lin_natural if e["max_spd"]]
        exp_max_n = [e["max_spd"] for e in exp_natural if e["max_spd"]]
        if lin_max_n and exp_max_n:
            U_n, p_n = mann_whitney(lin_max_n, exp_max_n)
            med_l_n = sorted(lin_max_n)[len(lin_max_n)//2]
            med_e_n = sorted(exp_max_n)[len(exp_max_n)//2]
            lines.append(f"  Mann-Whitney max SPD at natural K: U={U_n:.0f} p={p_n:.4g}")
            lines.append(f"  Medians: linear={med_l_n}  exponential={med_e_n}")

    lines.append("\n" + "=" * 70)
    lines.append("End of report")
    lines.append("=" * 70)

    text = "\n".join(lines)
    with open(report_path, "w") as f:
        f.write(text)
    print(text)
    print(f"\n  report saved → {report_path}")


# ─────────────────────────────────────────────────────────────────────────────
# CSV exports
# ─────────────────────────────────────────────────────────────────────────────

def export_summary_csv(summary: list[dict], path: Path):
    fields = ["instance", "K", "tag", "completeness", "n_computed",
              "max_spd", "min_spd", "last_spd", "peak_ratio", "growth_class"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(summary)
    print(f"  saved → {path}")


def export_growth_csv(summary: list[dict], path: Path):
    classifiable = [r for r in summary
                    if r["growth_class"] not in ("none", "insufficient")]
    fields = ["instance", "K", "tag", "growth_class", "max_spd", "min_spd",
              "last_spd", "peak_ratio", "n_computed", "completeness"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(classifiable)
    print(f"  saved → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SPD complexity analysis")
    parser.add_argument("--out_dir", default="figures/spd_analysis",
                        help="Output directory for figures and CSVs")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading instance tags …")
    lin_set, exp_set = load_tags()
    print(f"  linear: {len(lin_set)} instances")
    print(f"  exponential: {len(exp_set)} instances")

    print("Loading SPD interpolant records …")
    records = load_spd_records()
    print(f"  loaded {len(records)} (instance, K) pairs with SPD data")

    print("Building summary …")
    summary = build_summary(records, lin_set, exp_set)
    print(f"  {len(summary)} rows in summary")

    print("\nExporting CSVs …")
    export_summary_csv(summary, out_dir / "spd_analysis_data.csv")
    export_growth_csv(summary, out_dir / "spd_growth_classified.csv")

    print("\nGenerating figures …")
    # Primary K value: 5 (has both linear and exponential data)
    # Secondary K value: 10 (linear-only, exponential all infeasible)
    Ks_with_both = []
    for K in sorted({r["K"] for r in summary}):
        has_lin = any(r["tag"] == "linear" and r["n_computed"] > 0 for r in summary if r["K"] == K)
        has_exp = any(r["tag"] == "exponential" and r["n_computed"] > 0 for r in summary if r["K"] == K)
        if has_lin or has_exp:
            Ks_with_both.append(K)

    plot_infeasibility_rates(summary, out_dir, Ks=sorted(set([5, 10]) & set(Ks_with_both))[:4])
    plot_trajectories(records, lin_set, exp_set, out_dir, K=5)
    plot_max_spd_distribution(summary, out_dir, K=5)
    plot_growth_confusion(summary, out_dir, K=5)
    plot_scatter_max_spd(summary, out_dir, K=5)
    plot_infeasibility_by_K(records, lin_set, exp_set, out_dir)

    print("\nBuilding natural-K map …")
    nat_K = build_natural_K_map(LINEAR_CSV, EXPONENTIAL_CSV)

    print("\nRunning statistical tests …")
    write_report(summary, records, lin_set, exp_set, nat_K,
                 report_path=out_dir / "spd_analysis_report.txt")

    print("\nDone.")


if __name__ == "__main__":
    main()
