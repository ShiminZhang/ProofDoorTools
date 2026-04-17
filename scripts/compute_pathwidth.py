import argparse
import json
import os
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Optional, Set
import networkx as nx
from utils.process_cnf import CNF

try:
    import wandb
except Exception:
    wandb = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_incidence_graph_from_clauses(clauses: list[list[int]]) -> nx.Graph:
    graph = nx.Graph()
    vars_in_block = sorted({abs(lit) for clause in clauses for lit in clause})

    for var in vars_in_block:
        graph.add_node(("v", int(var)))

    for clause_idx, clause in enumerate(clauses):
        clause_node = ("c", clause_idx)
        graph.add_node(clause_node)
        for lit in clause:
            graph.add_edge(("v", abs(int(lit))), clause_node)

    return graph


def iter_clause_ranges(cnf: CNF):
    for iter_idx in range(cnf.K + 1):
        start = cnf.iter_map[iter_idx]
        end = cnf.iter_map[iter_idx + 1] if iter_idx < cnf.K else len(cnf.clauses)
        yield iter_idx, start, end


def _current_ordering(graph: nx.Graph) -> list:
    return list(graph.nodes())


def _vertex_separation_width(graph: nx.Graph, ordering: list) -> int:
    pos = {node: i for i, node in enumerate(ordering)}
    prefix = []
    width = 0

    for i, node in enumerate(ordering):
        prefix.append(node)
        frontier_size = 0
        for u in prefix:
            for nb in graph.neighbors(u):
                if pos[nb] > i:
                    frontier_size += 1
                    break
        width = max(width, frontier_size)

    return width


def compute_pathwidth_upper_bound(graph: nx.Graph) -> int:
    if graph.number_of_nodes() <= 1:
        return 0
    ordering = _current_ordering(graph)
    return _vertex_separation_width(graph, ordering)


def _parse_k_values(raw_k: str) -> list[int]:
    if not raw_k:
        return []
    values = []
    for token in raw_k.split(","):
        token = token.strip()
        if not token:
            continue
        values.append(int(token))
    return sorted(set(values))


def _plot_per_iteration(results: list[dict], output_path: str, cnf_label: str, mode: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise RuntimeError(
            "plotting requires matplotlib. Install it in your environment and retry with --plot."
        ) from exc

    xs = [int(r["iter"]) for r in results]
    ys_pw = [int(r["pathwidth_upper_bound"]) for r in results]
    ys_clauses = [int(r["num_clauses"]) for r in results]

    fig, ax1 = plt.subplots(figsize=(8, 4.5))
    ax1.plot(xs, ys_pw, marker="o", linewidth=1.8, color="#1f77b4", label="pathwidth_upper_bound")
    ax1.set_xlabel("iteration")
    ax1.set_ylabel("pathwidth_upper_bound", color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")
    ax1.grid(True, linestyle="--", alpha=0.35)

    ax2 = ax1.twinx()
    ax2.plot(xs, ys_clauses, marker="x", linewidth=1.2, color="#ff7f0e", label="num_clauses")
    ax2.set_ylabel("num_clauses", color="#ff7f0e")
    ax2.tick_params(axis="y", labelcolor="#ff7f0e")

    title = f"pathwidth by iteration ({mode})"
    if cnf_label:
        title += f"\n{os.path.basename(cnf_label)}"
    fig.suptitle(title)
    fig.tight_layout()

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def _discover_cnf_tasks(
    k_values: list[int],
    instance_filter: Optional[Set[str]] = None,
    plot_dir_root: str = os.path.join("temp", "pathwidth", "plots"),
) -> list[dict]:
    tasks = []
    for k in k_values:
        cnf_dir = os.path.join("ProofDoorBenchmark", "cnfs", str(k))
        if not os.path.isdir(cnf_dir):
            print(f"[manage] skip K={k}, directory not found: {cnf_dir}")
            continue

        suffix = f".{k}.cnf"
        for filename in sorted(os.listdir(cnf_dir)):
            if not filename.endswith(suffix):
                continue
            instance = filename[: -len(suffix)]
            if instance_filter is not None and instance not in instance_filter:
                continue
            cnf_path = os.path.join(cnf_dir, filename)
            out_path = os.path.join("temp", "pathwidth", str(k), f"{instance}.{k}.pathwidth.json")
            plot_path = os.path.join(plot_dir_root, str(k), f"{instance}.{k}.pathwidth.png")
            tasks.append(
                {
                    "instance": instance,
                    "K": k,
                    "cnf_path": cnf_path,
                    "out_path": out_path,
                    "plot_path": plot_path,
                }
            )
    return tasks


def _submit_sbatch(job_name: str, output_log: str, wrapped_cmd: str, mem: str, time_limit: str, dependency: str = "") -> str:
    os.makedirs(os.path.dirname(output_log), exist_ok=True)
    cmd = [
        "sbatch",
        f"--job-name={job_name}",
        f"--output={output_log}",
        f"--mem={mem}",
        f"--time={time_limit}",
        "--cpus-per-task=1",
    ]
    if dependency:
        cmd.append(f"--dependency={dependency}")
    cmd.append(f'--wrap={wrapped_cmd}')
    out = subprocess.check_output(cmd, text=True).strip()
    # expected: Submitted batch job <id>
    job_id = out.split()[-1]
    return job_id


def run_manage(args) -> None:
    if shutil.which("sbatch") is None:
        raise RuntimeError("sbatch not found in PATH; cannot run --manage")

    k_values = _parse_k_values(args.K)
    if not k_values:
        raise ValueError("--manage requires --K (e.g., --K 10 or --K 10,20)")

    instance_filter = None
    if args.instances:
        instance_filter = {x.strip() for x in args.instances.split(",") if x.strip()}
        if not instance_filter:
            instance_filter = None

    tasks = _discover_cnf_tasks(
        k_values,
        instance_filter=instance_filter,
        plot_dir_root=args.plot_dir,
    )
    if not tasks:
        print("[manage] no CNF tasks found to submit")
        return

    os.makedirs(os.path.join("temp", "pathwidth"), exist_ok=True)
    os.makedirs(os.path.join("results"), exist_ok=True)

    job_ids = []
    for task in tasks:
        k = task["K"]
        instance = task["instance"]
        cnf_path = task["cnf_path"]
        out_path = task["out_path"]
        plot_path = task["plot_path"]
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        inner_cmd = (
            "PYTHONPATH=. python scripts/compute_pathwidth.py "
            f"--cnf {shlex.quote(cnf_path)} "
            f"--mode {shlex.quote(args.mode)} "
            f"--out {shlex.quote(out_path)}"
        )
        if args.plot:
            inner_cmd += f" --plot --plot-out {shlex.quote(plot_path)}"
        job_name = f"pw_{instance}.{k}"[:120]
        output_log = os.path.join("SlurmLogs", "pathwidth", str(k), f"{instance}.{k}.%j.log")
        job_id = _submit_sbatch(
            job_name=job_name,
            output_log=output_log,
            wrapped_cmd=inner_cmd,
            mem=args.mem,
            time_limit=args.time,
        )
        print(f"[manage] submitted {instance}.{k} -> job {job_id}")
        job_ids.append(job_id)

    ks_tag = "_".join(str(k) for k in k_values)
    summary_output = os.path.join("results", f"pathwidth_summary_k_{ks_tag}_{args.mode}.json")
    summary_plot_output = os.path.join("figures", f"pathwidth_k_{ks_tag}_{args.mode}.png")
    summary_cmd = (
        "PYTHONPATH=. python scripts/summarize_pathwidth_results.py "
        f"--input-dir {shlex.quote(os.path.join('temp', 'pathwidth'))} "
        f"--output {shlex.quote(summary_output)} "
        f"--mode {shlex.quote(args.mode)} "
        f"--K {shlex.quote(args.K)} "
        f"--plot --plot-out {shlex.quote(summary_plot_output)}"
    )
    dep = "afterany:" + ":".join(job_ids)
    summary_job_id = _submit_sbatch(
        job_name=f"pw_sum_{ks_tag}"[:120],
        output_log=os.path.join("SlurmLogs", "pathwidth", f"summary_{ks_tag}.%j.log"),
        wrapped_cmd=summary_cmd,
        mem=args.summary_mem,
        time_limit=args.summary_time,
        dependency=dep,
    )

    print(f"[manage] submitted {len(tasks)} worker jobs")
    print(f"[manage] summary job id: {summary_job_id}")
    print(f"[manage] summary output path: {summary_output}")


def run_single(args) -> None:
    cnf = args.cnf
    mode = args.mode
    use_wandb = args.wandb and wandb is not None

    if use_wandb:
        wandb.init(project="pathwidth", name=f"{cnf}-{mode}")
        wandb.log({"cnf": cnf, "mode": mode})

    cnf_obj = CNF.from_file(cnf)
    per_iter_results = []
    for iter_idx, start, end in iter_clause_ranges(cnf_obj):
        clauses = cnf_obj.clauses[start:end] if mode == "block" else cnf_obj.clauses[:end]
        graph = build_incidence_graph_from_clauses(clauses)
        pathwidth_upper_bound = compute_pathwidth_upper_bound(graph)
        result = {
            "iter": iter_idx,
            "start_clause_idx": start,
            "end_clause_idx": end,
            "num_clauses": len(clauses),
            "pathwidth_upper_bound": pathwidth_upper_bound,
        }
        per_iter_results.append(result)
        print(
            f"iter {iter_idx}: pathwidth_upper_bound={pathwidth_upper_bound}, "
            f"num_clauses={len(clauses)}, range=[{start},{end})"
        )
        if use_wandb:
            wandb.log(result)

    max_pw = max((item["pathwidth_upper_bound"] for item in per_iter_results), default=0)
    payload = {
        "cnf": cnf,
        "mode": mode,
        "generated_at": _now_iso(),
        "num_iterations": len(per_iter_results),
        "max_pathwidth_upper_bound": max_pw,
        "per_iteration": per_iter_results,
    }

    if args.plot:
        plot_out = args.plot_out
        if not plot_out:
            base = os.path.basename(cnf)
            if base.endswith(".cnf"):
                base = base[: -len(".cnf")]
            plot_out = os.path.join("temp", "pathwidth", "plots", f"{base}.{mode}.pathwidth.png")
        _plot_per_iteration(per_iter_results, plot_out, cnf, mode)
        payload["plot_path"] = plot_out
        print(f"wrote_plot: {plot_out}")

    if args.out:
        out_dir = os.path.dirname(args.out)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        print(f"wrote_json: {args.out}")

    if use_wandb:
        wandb.log({"max_pathwidth_upper_bound": max_pw})
        wandb.finish()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cnf", type=str, help="Path to a single CNF file for local computation.")
    parser.add_argument(
        "--mode",
        type=str,
        default="block",
        choices=["block", "prefix"],
        help="block: per-iteration clauses only; prefix: clauses from start to this iteration",
    )
    parser.add_argument("--out", type=str, default="", help="Optional JSON output path for single CNF mode.")
    parser.add_argument("--plot", action="store_true", help="Generate per-iteration pathwidth plot (PNG).")
    parser.add_argument(
        "--plot-out",
        type=str,
        default="",
        help="Optional plot output path for single CNF mode (used only with --plot).",
    )
    parser.add_argument(
        "--plot-dir",
        type=str,
        default=os.path.join("temp", "pathwidth", "plots"),
        help="Plot output directory root for --manage (used only with --plot).",
    )
    parser.add_argument("--manage", action="store_true", help="Submit pathwidth jobs for many CNFs via Slurm.")
    parser.add_argument("--K", type=str, default="", help="K value(s) for --manage. Example: 10 or 10,20,40")
    parser.add_argument(
        "--instances",
        type=str,
        default="",
        help="Optional comma-separated instance filter for --manage.",
    )
    parser.add_argument("--mem", type=str, default="10g", help="Slurm memory per worker job in --manage mode.")
    parser.add_argument("--time", type=str, default="12:00:00", help="Slurm time per worker job in --manage mode.")
    parser.add_argument("--summary-mem", type=str, default="10g", help="Slurm memory for summary job.")
    parser.add_argument("--summary-time", type=str, default="12:30:00", help="Slurm time for summary job.")
    parser.add_argument("--wandb", action="store_true", help="Enable wandb logging.")
    args = parser.parse_args()

    if args.manage:
        run_manage(args)
        return

    if not args.cnf:
        raise ValueError("single CNF mode requires --cnf (or use --manage)")
    run_single(args)

if __name__ == "__main__":
    main()