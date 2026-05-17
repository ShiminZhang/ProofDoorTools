import json
import os
import shlex
import shutil
import subprocess
import sys
import argparse
from pathlib import Path

import community as community_louvain
import networkx as nx

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
os.chdir(REPO_ROOT)
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from utils.paths import get_CNF_dir
from utils.utils import generate_cnf

REGRESSION_SUMMARY_CSV = os.path.join(REPO_ROOT, "regression_summary.csv")


def get_instances_from_regression(category=None):
    import csv
    names = []
    with open(REGRESSION_SUMMARY_CSV, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if category is None or category == "all" or row["best_model"].strip().lower() == category.lower():
                names.append(row["instance_name"].strip())
    return names

OUTPUT_DIR_TEMPLATE = "./ProofDoorBenchmark/cnf_modularity/{K}/"
SLURM_LOG_DIR_TEMPLATE = "./SlurmLogs/cnf_modularity/{K}/"


def get_output_path(name, K):
    d = OUTPUT_DIR_TEMPLATE.format(K=K)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{name}.{K}.modularity.json")


def read_cnf(path):
    clauses = []
    maxvar = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in ('c', 'p'):
                continue
            lits = [int(x) for x in line.split() if x != '0']
            for lit in lits:
                maxvar = max(maxvar, abs(lit))
            clauses.append(lits)
    return maxvar, clauses


def build_vig(clauses):
    """Build a weighted Variable Incidence Graph (VIG).

    Standard weighting: each clause of length k contributes 1/C(k,2) to each
    variable pair, so large clauses don't dominate.
    """
    weights = {}
    for clause in clauses:
        vars_in_clause = sorted(set(abs(lit) for lit in clause))
        k = len(vars_in_clause)
        if k < 2:
            continue
        w = 1.0 / (k * (k - 1) / 2.0)
        for i in range(k):
            for j in range(i + 1, k):
                key = (vars_in_clause[i], vars_in_clause[j])
                weights[key] = weights.get(key, 0.0) + w

    G = nx.Graph()
    for (u, v), w in weights.items():
        G.add_edge(u, v, weight=w)
    return G


def ensure_cnf(name, K):
    """Generate the CNF if it is missing or empty."""
    cnf_path = os.path.join(get_CNF_dir(K), f"{name}.{K}.cnf")
    if not os.path.exists(cnf_path) or os.path.getsize(cnf_path) == 0:
        print(f"[cnf] {cnf_path} not found, generating...")
        generate_cnf(f"{name}.{K}.cnf")
    return cnf_path


def compute_modularity(name, K, seed=1, out=None):
    cnf_path = ensure_cnf(name, K)
    if not os.path.exists(cnf_path) or os.path.getsize(cnf_path) == 0:
        raise FileNotFoundError(f"CNF not found after generation attempt: {cnf_path}")

    maxvar, clauses = read_cnf(cnf_path)
    print(f"CNF:         {name}.{K}.cnf")
    print(f"Variables:   {maxvar}")
    print(f"Clauses:     {len(clauses)}")

    G = build_vig(clauses)
    print(f"VIG nodes:   {G.number_of_nodes()}  edges: {G.number_of_edges()}")

    partition = community_louvain.best_partition(G, weight='weight', random_state=seed)
    Q = community_louvain.modularity(partition, G, weight='weight')
    n_communities = len(set(partition.values()))

    print(f"Communities: {n_communities}")
    print(f"Modularity:  {Q:.6f}")

    if out:
        payload = {
            "name": name,
            "K": K,
            "n_vars": maxvar,
            "n_clauses": len(clauses),
            "vig_nodes": G.number_of_nodes(),
            "vig_edges": G.number_of_edges(),
            "n_communities": n_communities,
            "modularity": Q,
            "seed": seed,
        }
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"Written:     {out}")

    return Q, n_communities, partition


def _submit_sbatch(job_name, output_log, wrapped_cmd, mem="10G", time_limit="10:00:00"):
    os.makedirs(os.path.dirname(output_log), exist_ok=True)
    cmd = [
        "sbatch",
        f"--job-name={job_name}",
        f"--output={output_log}",
        f"--mem={mem}",
        f"--time={time_limit}",
        "--cpus-per-task=1",
        f"--wrap={wrapped_cmd}",
    ]
    out = subprocess.check_output(cmd, text=True).strip()
    return out.split()[-1]


def run_manage(args):
    if shutil.which("sbatch") is None:
        raise RuntimeError("sbatch not found in PATH; cannot run --manage")

    # Collect instance names
    if args.category:
        names = get_instances_from_regression(args.category)
        if not names:
            raise ValueError(f"No instances found for category '{args.category}'")
    elif args.name:
        names = [args.name]
    else:
        raise ValueError("--manage requires --category or --name")

    K = args.K
    submitted = 0
    for name in names:
        out_path = get_output_path(name, K)
        inner_cmd = (
            f"PYTHONPATH=. python scripts/compute_cnf_modularity.py "
            f"--name {shlex.quote(name)} "
            f"--K {K} "
            f"--seed {args.seed} "
            f"--out {shlex.quote(out_path)}"
        )
        job_name = f"mod_{name}.{K}"[:120]
        log_dir = SLURM_LOG_DIR_TEMPLATE.format(K=K)
        output_log = os.path.join(log_dir, f"{name}.{K}.%j.log")
        job_id = _submit_sbatch(
            job_name=job_name,
            output_log=output_log,
            wrapped_cmd=inner_cmd,
            mem=args.mem,
            time_limit=args.time,
        )
        print(f"[manage] submitted {name}.{K} -> job {job_id}")
        submitted += 1

    print(f"[manage] {submitted} job(s) submitted for K={K}")


def run_collect(K, plot_out=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    result_dir = OUTPUT_DIR_TEMPLATE.format(K=K)
    if not os.path.isdir(result_dir):
        raise FileNotFoundError(f"No results directory found: {result_dir}")

    by_category = {}
    for fname in sorted(os.listdir(result_dir)):
        if not fname.endswith(".modularity.json"):
            continue
        with open(os.path.join(result_dir, fname)) as f:
            data = json.load(f)
        name = data["name"]
        Q = data["modularity"]

        # look up category from regression summary
        cat = "unknown"
        try:
            import csv
            with open(REGRESSION_SUMMARY_CSV, newline='') as cf:
                for row in csv.DictReader(cf):
                    if row["instance_name"].strip() == name:
                        cat = row["best_model"].strip().lower()
                        break
        except Exception:
            pass

        by_category.setdefault(cat, []).append(Q)

    if not by_category:
        print(f"[collect] no results found in {result_dir}")
        return

    categories = sorted(by_category)
    data_groups = [by_category[c] for c in categories]
    labels = [f"{c}\n({len(by_category[c])} instances)" for c in categories]

    fig, ax = plt.subplots(figsize=(max(6, 2 * len(categories)), 5))
    ax.boxplot(data_groups, labels=labels, patch_artist=True)
    ax.set_ylabel("Modularity (Q)")
    ax.set_title("BMC Formula Community Structure Modularity")
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    fig.tight_layout()

    if plot_out is None:
        os.makedirs("figures", exist_ok=True)
        plot_out = f"figures/cnf_modularity_K{K}.png"
    os.makedirs(os.path.dirname(plot_out) or ".", exist_ok=True)
    fig.savefig(plot_out, dpi=180, bbox_inches="tight")
    plt.close(fig)

    total = sum(len(v) for v in by_category.values())
    print(f"[collect] {total} results across {len(categories)} categories -> {plot_out}")
    for c in categories:
        qs = by_category[c]
        print(f"  {c}: n={len(qs)}  mean={sum(qs)/len(qs):.4f}  "
              f"min={min(qs):.4f}  max={max(qs):.4f}")


def main():
    parser = argparse.ArgumentParser(
        description='Compute VIG community structure modularity of a CNF formula'
    )
    parser.add_argument('--name',     help='Instance name (single mode or manage override)')
    parser.add_argument('--K',        type=int, required=True, help='K value')
    parser.add_argument('--seed',     type=int, default=1, help='Louvain random seed')
    parser.add_argument('--out',      help='Path to write JSON result')
    parser.add_argument('--manage',   action='store_true',
                        help='Submit one Slurm job per instance')
    parser.add_argument('--collect',  action='store_true',
                        help='Collect results for K and draw a box plot by category')
    parser.add_argument('--plot-out', dest='plot_out',
                        help='Output path for the box plot (default: figures/cnf_modularity_K{K}.png)')
    parser.add_argument('--category', help='Instance category (linear/polynomial/exponential/all) for --manage')
    parser.add_argument('--mem',      default='10G', help='Slurm memory per job (default: 10G)')
    parser.add_argument('--time',     default='10:00:00', help='Slurm time limit per job (default: 10:00:00)')
    args = parser.parse_args()

    if args.manage:
        run_manage(args)
        return

    if args.collect:
        run_collect(args.K, plot_out=args.plot_out)
        return

    if not args.name:
        parser.error("--name is required in single mode")

    out = args.out or get_output_path(args.name, args.K)
    compute_modularity(args.name, args.K, seed=args.seed, out=out)


if __name__ == '__main__':
    main()
