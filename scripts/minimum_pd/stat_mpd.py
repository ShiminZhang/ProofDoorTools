import argparse
import csv
import glob
import html
import math
import os
from collections import defaultdict
from typing import Dict, Iterable, List, Optional

SLURM_LOG_DIR = "./SlurmLogs/compute_mpd"
REGRESSION_SUMMARY_PATH = "./regression_summary.csv"
INTERPOLANT_DIR_TEMPLATE = "./ProofDoorBenchmark/interpolants_def6/{K}"


def load_instance_categories() -> Dict[str, str]:
    categories: Dict[str, str] = {}
    with open(REGRESSION_SUMMARY_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            categories[row["instance_name"]] = row["best_model"]
    return categories


def get_target_names(
    categories: Dict[str, str],
    name: Optional[str] = None,
    category: Optional[str] = None,
) -> List[str]:
    if name is not None:
        return [name]

    names = sorted(categories)
    if category is not None:
        names = [inst for inst in names if categories.get(inst) == category]
    return names


def get_log_paths(name: str, K: int, index: int) -> List[str]:
    pattern = os.path.join(SLURM_LOG_DIR, f"k_{K}", f"{name}.{K}.*_{index}.log")
    return sorted(glob.glob(pattern))


def log_indicates_success(log_path: str, name: str, K: int, index: int) -> bool:
    success_str = f"Interpolant validity check passed for {name}.{K}.{index}"
    with open(log_path) as f:
        return success_str in f.read()


def compute_success(name: str, K: int, index: int, interpolant_path: str) -> bool:
    log_paths = get_log_paths(name, K, index)
    if log_paths:
        return any(log_indicates_success(p, name, K, index) for p in log_paths)
    return os.path.exists(interpolant_path)


def count_clauses(interpolant_path: str) -> int:
    n_of_clauses = 0
    with open(interpolant_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line[0] in ("c", "p", "a", "e"):
                continue
            n_of_clauses += 1
    return n_of_clauses


def build_rows(
    names: Iterable[str],
    categories: Dict[str, str],
    K_values: Iterable[int],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []

    for name in names:
        inst_category = categories.get(name, "unknown")
        for K in K_values:
            interpolant_dir = INTERPOLANT_DIR_TEMPLATE.format(K=K)
            for index in range(K):
                log_paths = get_log_paths(name, K, index)
                if not log_paths:
                    continue
                interpolant_path = os.path.join(interpolant_dir, f"{name}.{K}.{index}.interpolant")
                ok = compute_success(name, K, index, interpolant_path)
                if ok and os.path.exists(interpolant_path):
                    n_of_clauses: int | str = count_clauses(interpolant_path)
                else:
                    n_of_clauses = "NA"
                rows.append(
                    {
                        "name": name,
                        "K": K,
                        "index": index,
                        "category": inst_category,
                        "compute_success": ok,
                        "n_of_clauses": n_of_clauses,
                    }
                )
    return rows


def write_rows(rows: List[Dict[str, object]], output_path: str) -> None:
    fieldnames = [
        "name",
        "K",
        "index",
        "category",
        "compute_success",
        "n_of_clauses",
    ]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_rows(input_path: str) -> List[Dict[str, object]]:
    with open(input_path, newline="") as f:
        return list(csv.DictReader(f))


def filter_rows(
    rows: List[Dict[str, object]],
    name: Optional[str] = None,
    category: Optional[str] = None,
) -> List[Dict[str, object]]:
    filtered = rows
    if name is not None:
        filtered = [row for row in filtered if str(row["name"]) == name]
    if category is not None:
        filtered = [row for row in filtered if str(row["category"]) == category]
    return filtered


def _parse_success(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _collect_plot_series(
    rows: List[Dict[str, object]],
) -> tuple[Dict[str, List[tuple[int, int]]], Dict[str, str]]:
    series_by_name: Dict[str, List[tuple[int, int]]] = defaultdict(list)
    category_by_name: Dict[str, str] = {}
    seen_sizes: Dict[tuple[str, int], int] = {}

    for row in rows:
        if not _parse_success(row["compute_success"]):
            continue
        if row["n_of_clauses"] == "NA":
            continue

        name = str(row["name"])
        index = int(row["index"])
        size = int(row["n_of_clauses"])
        category = str(row["category"])
        key = (name, index)

        prev_size = seen_sizes.get(key)
        if prev_size is not None:
            if prev_size != size:
                print(
                    f"WARNING: inconsistent size for {name} index={index}: "
                    f"{prev_size} vs {size}; keeping first value"
                )
            continue

        seen_sizes[key] = size
        category_by_name[name] = category
        series_by_name[name].append((index, size))

    if not series_by_name:
        raise RuntimeError("no successful MPD rows available for plotting")

    for name in series_by_name:
        series_by_name[name].sort(key=lambda item: item[0])

    return series_by_name, category_by_name


def _percentile(values: List[int], pct: float) -> float:
    if not values:
        raise ValueError("cannot compute percentile of empty list")
    if pct <= 0:
        return float(min(values))
    if pct >= 100:
        return float(max(values))

    values = sorted(values)
    pos = (len(values) - 1) * (pct / 100.0)
    lower = math.floor(pos)
    upper = math.ceil(pos)
    if lower == upper:
        return float(values[lower])
    weight = pos - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _trim_series_by_percentile(
    series_by_name: Dict[str, List[tuple[int, int]]],
    category_by_name: Dict[str, str],
    trim_y: Optional[float],
) -> tuple[Dict[str, List[tuple[int, int]]], Dict[str, str]]:
    if trim_y is None:
        return series_by_name, category_by_name

    max_by_name = {
        name: max(size for _, size in points)
        for name, points in series_by_name.items()
    }
    threshold = _percentile(list(max_by_name.values()), trim_y)

    kept_names = [name for name, max_size in max_by_name.items() if max_size <= threshold]
    trimmed_series = {name: series_by_name[name] for name in kept_names}
    trimmed_categories = {name: category_by_name[name] for name in kept_names}
    ignored = len(series_by_name) - len(trimmed_series)
    print(
        f"trim_y={trim_y} kept {len(trimmed_series)} names, "
        f"ignored {ignored} names, threshold={threshold:.2f}"
    )

    if not trimmed_series:
        raise RuntimeError("trim_y filtered out all names")

    return trimmed_series, trimmed_categories


def _collect_extend_segments(
    rows: List[Dict[str, object]],
    series_by_name: Dict[str, List[tuple[int, int]]],
) -> Dict[str, tuple[int, int]]:
    kept_names = set(series_by_name)
    observed_indices = set()
    max_success_y = max(size for points in series_by_name.values() for _, size in points)

    for row in rows:
        name = str(row["name"])
        if name not in kept_names:
            continue
        index = int(row["index"])
        observed_indices.add(index)

    extend_segments: Dict[str, tuple[int, int]] = {}
    if not observed_indices:
        return extend_segments
    global_max_index = max(observed_indices)
    for name, points in series_by_name.items():
        last_success_index = max(index for index, _ in points)
        if last_success_index >= global_max_index:
            continue
        a = last_success_index + 1
        if a == 1:
            continue
        b = 1.5 * max_success_y
        extend_segments[name] = (a, b)

    return extend_segments


def _write_svg_plot(
    series_by_name: Dict[str, List[tuple[int, int]]],
    category_by_name: Dict[str, str],
    extend_segments: Dict[str, tuple[int, int]],
    output_path: str,
) -> None:
    category_colors = {
        "linear": "orange",
        "exponential": "blue",
    }
    width = 1200
    height = 700
    margin_left = 90
    margin_right = 30
    margin_top = 50
    margin_bottom = 70
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    xs = [index for points in series_by_name.values() for index, _ in points]
    ys = [size for points in series_by_name.values() for _, size in points]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)

    if min_x == max_x:
        max_x += 1
    if min_y == max_y:
        max_y += 1

    def x_to_svg(x: int) -> float:
        return margin_left + (x - min_x) * plot_width / (max_x - min_x)

    def y_to_svg(y: float) -> float:
        return margin_top + plot_height - (y - min_y) * plot_height / (max_y - min_y)

    x_ticks = sorted(set(xs))
    if len(x_ticks) > 12:
        step = math.ceil(len(x_ticks) / 12)
        x_ticks = x_ticks[::step]
        if x_ticks[-1] != max_x:
            x_ticks.append(max_x)

    y_ticks = 6
    y_tick_values = [min_y + (max_y - min_y) * i / y_ticks for i in range(y_ticks + 1)]

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<defs><clipPath id="plot-area-clip"><rect x="{margin_left}" y="{margin_top}" width="{plot_width}" height="{plot_height}"/></clipPath></defs>',
        f'<text x="{width / 2}" y="30" text-anchor="middle" font-size="22" font-family="sans-serif">MPD Interpolant Size by Index</text>',
    ]

    for tick in x_ticks:
        x = x_to_svg(tick)
        parts.append(
            f'<line x1="{x:.2f}" y1="{margin_top}" x2="{x:.2f}" y2="{margin_top + plot_height}" stroke="#dddddd" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{x:.2f}" y="{height - margin_bottom + 25}" text-anchor="middle" font-size="12" font-family="sans-serif">{tick}</text>'
        )

    for tick in y_tick_values:
        y = y_to_svg(tick)
        label = f"{int(round(tick))}"
        parts.append(
            f'<line x1="{margin_left}" y1="{y:.2f}" x2="{margin_left + plot_width}" y2="{y:.2f}" stroke="#dddddd" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{margin_left - 10}" y="{y + 4:.2f}" text-anchor="end" font-size="12" font-family="sans-serif">{label}</text>'
        )

    parts.append(
        f'<line x1="{margin_left}" y1="{margin_top + plot_height}" x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" stroke="black" stroke-width="1.5"/>'
    )
    parts.append(
        f'<line x1="{margin_left}" y1="{margin_top}" x2="{margin_left}" y2="{margin_top + plot_height}" stroke="black" stroke-width="1.5"/>'
    )
    parts.append(
        f'<text x="{width / 2}" y="{height - 20}" text-anchor="middle" font-size="16" font-family="sans-serif">index</text>'
    )
    parts.append(
        f'<text x="25" y="{height / 2}" text-anchor="middle" font-size="16" font-family="sans-serif" transform="rotate(-90 25 {height / 2})">size</text>'
    )

    parts.append('<g clip-path="url(#plot-area-clip)">')
    for name in sorted(series_by_name):
        points = series_by_name[name]
        color = category_colors.get(category_by_name.get(name, "unknown"), "gray")
        point_str = " ".join(f"{x_to_svg(x):.2f},{y_to_svg(y):.2f}" for x, y in points)
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="1.5" stroke-opacity="0.8" points="{point_str}"/>'
        )
        for x, y in points:
            parts.append(
                f'<circle cx="{x_to_svg(x):.2f}" cy="{y_to_svg(y):.2f}" r="2.2" fill="{color}">'
                f"<title>{html.escape(name)} index={x} size={y}</title></circle>"
            )
        if name in extend_segments:
            a, b = extend_segments[name]
            last_x, last_y = points[-1]
            parts.append(
                f'<line x1="{x_to_svg(last_x):.2f}" y1="{y_to_svg(last_y):.2f}" '
                f'x2="{x_to_svg(a):.2f}" y2="{y_to_svg(b):.2f}" '
                f'stroke="{color}" stroke-width="1.5" stroke-opacity="0.8" stroke-dasharray="5,4"/>'
            )
            parts.append(
                f'<circle cx="{x_to_svg(a):.2f}" cy="{y_to_svg(b):.2f}" r="2.2" fill="{color}">'
                f"<title>{html.escape(name)} extend-to index={a} size={b}</title></circle>"
            )
    parts.append("</g>")

    legend_x = width - margin_right - 170
    legend_y = margin_top + 10
    parts.append(f'<rect x="{legend_x}" y="{legend_y}" width="150" height="52" fill="white" stroke="#cccccc"/>')
    parts.append(
        f'<line x1="{legend_x + 12}" y1="{legend_y + 18}" x2="{legend_x + 42}" y2="{legend_y + 18}" stroke="orange" stroke-width="2"/>'
    )
    parts.append(
        f'<text x="{legend_x + 50}" y="{legend_y + 22}" font-size="13" font-family="sans-serif">linear</text>'
    )
    parts.append(
        f'<line x1="{legend_x + 12}" y1="{legend_y + 38}" x2="{legend_x + 42}" y2="{legend_y + 38}" stroke="blue" stroke-width="2"/>'
    )
    parts.append(
        f'<text x="{legend_x + 50}" y="{legend_y + 42}" font-size="13" font-family="sans-serif">exponential</text>'
    )
    parts.append("</svg>")

    with open(output_path, "w") as f:
        f.write("\n".join(parts))


def plot_rows(
    rows: List[Dict[str, object]],
    output_path: str,
    trim_y: Optional[float] = None,
    extendx2: bool = False,
) -> str:
    series_by_name, category_by_name = _collect_plot_series(rows)
    series_by_name, category_by_name = _trim_series_by_percentile(
        series_by_name, category_by_name, trim_y
    )
    extend_segments = _collect_extend_segments(rows, series_by_name) if extendx2 else {}
    if output_path.lower().endswith(".png"):
        output_path = os.path.splitext(output_path)[0] + ".svg"
        print(f"WARNING: matplotlib not available; writing SVG instead: {output_path}")
    _write_svg_plot(series_by_name, category_by_name, extend_segments, output_path)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Collect minimum-PD computation status and interpolant clause counts "
            "into a CSV file."
        )
    )
    parser.add_argument("--K", type=int, required=True, help="K value")
    parser.add_argument(
        "--K_max",
        type=int,
        default=None,
        help="When set, export all K in [--K, --K_max]",
    )
    parser.add_argument("--name", help="Only export rows for one instance")
    parser.add_argument(
        "--category",
        help="Only export rows for instances in this regression_summary category",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="CSV output path (default: ./mpd_stats_k_<K>.csv)",
    )
    parser.add_argument(
        "--input_csv",
        default=None,
        help="Reuse an existing CSV summary instead of rescanning logs/interpolants",
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Plot one size-vs-index line per instance using any successful K row",
    )
    parser.add_argument(
        "--plot_output",
        default=None,
        help="Plot output path (default: CSV path with .png suffix)",
    )
    parser.add_argument(
        "--trim_y",
        type=float,
        default=None,
        help="Ignore names whose max size is above this percentile before plotting",
    )
    parser.add_argument(
        "--extendx2",
        action="store_true",
        help="Extend a name's last successful point to the first later failed index using 2x global max y at the next x",
    )
    args = parser.parse_args()

    if args.K_max is not None and args.K_max < args.K:
        raise ValueError("--K_max must be >= --K")
    if args.trim_y is not None and not (0 <= args.trim_y <= 100):
        raise ValueError("--trim_y must be between 0 and 100")

    K_values = list(range(args.K, args.K_max + 1)) if args.K_max is not None else [args.K]
    if args.output is not None:
        output_path = args.output
    elif len(K_values) == 1:
        output_path = f"./mpd_stats_k_{args.K}.csv"
    else:
        output_path = f"./mpd_stats_k_{K_values[0]}_to_{K_values[-1]}.csv"

    if args.input_csv is not None:
        rows = read_rows(args.input_csv)
        rows = filter_rows(rows, name=args.name, category=args.category)
        print(f"Loaded {len(rows)} rows from: {args.input_csv}")
    else:
        categories = load_instance_categories()
        names = get_target_names(categories, name=args.name, category=args.category)
        rows = build_rows(names, categories, K_values)
        write_rows(rows, output_path)
        print(f"Wrote {len(rows)} rows to: {output_path}")

    if args.plot:
        plot_output_path = args.plot_output or os.path.splitext(output_path)[0] + ".png"
        actual_plot_output_path = plot_rows(
            rows,
            plot_output_path,
            trim_y=args.trim_y,
            extendx2=args.extendx2,
        )
        print(f"Wrote plot to: {actual_plot_output_path}")


if __name__ == "__main__":
    main()
