#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime, timezone
from typing import Optional, Tuple


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_k_values(raw_k: str) -> list[int]:
    if not raw_k:
        return []
    out = []
    for token in raw_k.split(","):
        token = token.strip()
        if not token:
            continue
        out.append(int(token))
    return sorted(set(out))


def _discover_result_files(input_dir: str, k_values: list[int]) -> list[str]:
    files = []
    if k_values:
        for k in k_values:
            k_dir = os.path.join(input_dir, str(k))
            if not os.path.isdir(k_dir):
                continue
            for name in sorted(os.listdir(k_dir)):
                if name.endswith(".pathwidth.json"):
                    files.append(os.path.join(k_dir, name))
        return files

    for root, _, names in os.walk(input_dir):
        for name in names:
            if name.endswith(".pathwidth.json"):
                files.append(os.path.join(root, name))
    return sorted(files)


def _extract_instance_k(cnf_path: str) -> Tuple[str, Optional[int]]:
    base = os.path.basename(cnf_path)
    if not base.endswith(".cnf"):
        return base, None
    stem = base[: -len(".cnf")]
    parts = stem.split(".")
    if len(parts) < 2:
        return stem, None
    k_token = parts[-1]
    try:
        k_value = int(k_token)
        instance = ".".join(parts[:-1])
        return instance, k_value
    except Exception:
        return stem, None


def summarize(input_dir: str, output_path: str, mode: str, k_values: list[int]) -> dict:
    files = _discover_result_files(input_dir, k_values)
    rows = []
    skipped = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            skipped.append({"path": path, "reason": f"json_load_error: {exc}"})
            continue

        cnf = str(payload.get("cnf", "")).strip()
        result_mode = str(payload.get("mode", "")).strip()
        if mode and result_mode and result_mode != mode:
            continue
        if not cnf:
            skipped.append({"path": path, "reason": "missing_cnf"})
            continue

        instance, k_value = _extract_instance_k(cnf)
        if k_values and (k_value is None or k_value not in k_values):
            continue

        per_iter = payload.get("per_iteration", [])
        max_pw = payload.get("max_pathwidth_upper_bound", None)
        if max_pw is None and isinstance(per_iter, list):
            vals = [r.get("pathwidth_upper_bound", 0) for r in per_iter if isinstance(r, dict)]
            max_pw = max(vals) if vals else 0

        rows.append(
            {
                "instance": instance,
                "K": k_value,
                "cnf": cnf,
                "mode": result_mode or mode,
                "num_iterations": int(payload.get("num_iterations", len(per_iter))),
                "max_pathwidth_upper_bound": int(max_pw) if max_pw is not None else None,
                "result_path": path,
            }
        )

    rows.sort(key=lambda r: (r["K"] if r["K"] is not None else -1, r["instance"]))

    by_k = {}
    for row in rows:
        k = row["K"]
        if k is None:
            continue
        ks = str(k)
        bucket = by_k.setdefault(
            ks,
            {"count": 0, "instances": [], "max_of_max_pathwidth_upper_bound": 0},
        )
        bucket["count"] += 1
        bucket["instances"].append(row["instance"])
        v = row["max_pathwidth_upper_bound"]
        if isinstance(v, int):
            bucket["max_of_max_pathwidth_upper_bound"] = max(bucket["max_of_max_pathwidth_upper_bound"], v)

    for bucket in by_k.values():
        bucket["instances"] = sorted(set(bucket["instances"]))

    summary = {
        "generated_at": _now_iso(),
        "input_dir": input_dir,
        "mode": mode,
        "ks": k_values,
        "num_results": len(rows),
        "num_skipped": len(skipped),
        "results": rows,
        "by_k": by_k,
        "skipped": skipped,
    }

    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    return summary


def _plot_k_vs_max_pathwidth(
    rows: list,
    output_path: str,
    mode: str,
    top_n: int = 0,
) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        raise RuntimeError(
            "plotting requires matplotlib. Install it in your environment."
        ) from exc

    from collections import defaultdict

    instance_data: dict[str, list[tuple]] = defaultdict(list)
    for row in rows:
        k = row.get("K")
        pw = row.get("max_pathwidth_upper_bound")
        inst = row.get("instance", "")
        if k is None or pw is None or not inst:
            continue
        instance_data[inst].append((int(k), int(pw)))

    for inst in instance_data:
        instance_data[inst].sort()

    if top_n > 0 and len(instance_data) > top_n:
        ranked = sorted(
            instance_data.items(),
            key=lambda kv: max(pw for _, pw in kv[1]),
            reverse=True,
        )
        top_instances = {inst for inst, _ in ranked[:top_n]}
    else:
        top_instances = set(instance_data.keys())

    fig, ax = plt.subplots(figsize=(10, 6))

    for inst in sorted(top_instances):
        pts = instance_data[inst]
        ks = [p[0] for p in pts]
        pws = [p[1] for p in pts]
        ax.plot(ks, pws, marker="o", markersize=3.5, linewidth=1.2, label=inst)

    ax.set_xlabel("K")
    ax.set_ylabel("max pathwidth upper bound (across iterations)")
    ax.grid(True, linestyle="--", alpha=0.35)

    title = "max pathwidth vs K"
    if mode:
        title += f" ({mode})"
    if top_n > 0 and len(instance_data) > top_n:
        title += f" (top {top_n} of {len(instance_data)} instances)"
    ax.set_title(title)

    if len(top_instances) <= 25:
        ax.legend(fontsize=7, ncol=2, loc="best")

    fig.tight_layout()
    out_dir = os.path.dirname(output_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize per-CNF pathwidth JSON results.")
    parser.add_argument("--input-dir", type=str, default=os.path.join("temp", "pathwidth"))
    parser.add_argument("--output", type=str, required=True, help="Output summary JSON path (usually under results/).")
    parser.add_argument("--mode", type=str, default="", choices=["", "block", "prefix"])
    parser.add_argument("--K", type=str, default="", help="Optional K filter, e.g. 10 or 10,20")
    parser.add_argument("--plot", action="store_true", help="Generate K vs max-pathwidth plot.")
    parser.add_argument(
        "--plot-out",
        type=str,
        default="",
        help="Plot output path (default: derived from --output with .png extension).",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=0,
        help="Plot only top N instances by max pathwidth (0 = all).",
    )
    args = parser.parse_args()

    k_values = _parse_k_values(args.K)
    summary = summarize(
        input_dir=args.input_dir,
        output_path=args.output,
        mode=args.mode,
        k_values=k_values,
    )
    print(f"summary_written: {args.output}")
    print(f"num_results: {summary['num_results']}")
    print(f"num_skipped: {summary['num_skipped']}")

    if args.plot:
        plot_out = args.plot_out
        if not plot_out:
            base, _ = os.path.splitext(args.output)
            plot_out = base + ".png"
        _plot_k_vs_max_pathwidth(
            rows=summary["results"],
            output_path=plot_out,
            mode=args.mode,
            top_n=args.top_n,
        )
        print(f"wrote_plot: {plot_out}")


if __name__ == "__main__":
    main()
