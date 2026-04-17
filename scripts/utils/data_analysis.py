import argparse
import os
import csv
import math
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from tqdm import tqdm
from aigverse import (  # type: ignore[import-not-found]
    DepthAig,
    read_aiger_into_aig,
    read_aiger_into_sequential_aig,
)
import sys
if "utils" not in sys.modules:
    from paths import get_aiger_dir, get_circuit_features_dir, get_CNF_dir
    from bits import theoretical_bits_smtcnf, theoretical_bits_dimacs
else:
    from utils.paths import get_aiger_dir, get_circuit_features_dir, get_CNF_dir
    from utils.bits import theoretical_bits_smtcnf, theoretical_bits_dimacs
import json
import matplotlib.pyplot as plt
import numpy as np


def _read_circuit_features(path: str) -> Dict[str, Dict[str, int]]:
    feats: Dict[str, Dict[str, int]] = {}
    with open(path, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            inst = row["instance_name"].strip()
            feats[inst] = {
                "nlatches": int(row["nlatches"]),
                "nands": int(row["nands"]),
                "noutputs": int(row["noutputs"]),
                "depth": int(row["depth"]),
            }
    return feats


def _find_pds_scaling_results_json(k: int) -> str:
    return _find_pds_scaling_results_json_by_pddef(
        k,
        pddef=1,
        preferred_tokens=["_ysolvingtime_", "_ysolvingtime", "xproofdoor_size"],
    )


def _find_pds_scaling_results_json_by_pddef(
    k: int,
    pddef: int,
    preferred_tokens: List[str] | None = None,
) -> str:
    result_dir = os.path.join("Experiments", "pds_scaling", "result")
    k_token = f"_K{int(k)}_"
    candidates = [
        os.path.join(result_dir, fn)
        for fn in os.listdir(result_dir)
        if fn.startswith("pds_scaling_results")
        and fn.endswith(".json")
        and (f"_pddef{int(pddef)}" in fn)
        and (k_token in fn)
    ]

    # Fallback for historical files that don't encode K in filename.
    if not candidates:
        candidates = [
            os.path.join(result_dir, fn)
            for fn in os.listdir(result_dir)
            if fn.startswith("pds_scaling_results")
            and fn.endswith(".json")
            and (f"_pddef{int(pddef)}" in fn)
        ]

    pool = candidates
    if preferred_tokens:
        preferred = [
            p for p in candidates if any(tok in os.path.basename(p) for tok in preferred_tokens)
        ]
        pool = preferred or candidates
    if not pool:
        raise FileNotFoundError(f"No pds_scaling_results json found for pddef={int(pddef)} K={int(k)}")
    pool.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return pool[0]


def _load_pds_scaling_points(path: str) -> Tuple[str, Dict[Tuple[str, int], Dict]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    out: Dict[Tuple[str, int], Dict] = {}
    for inst, pts in payload["instances"].items():
        for p in pts:
            out[(inst, int(p["K"]))] = p
    return path, out


def _parse_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        try:
            fv = float(value)
            if math.isfinite(fv) and fv.is_integer():
                return int(fv)
        except Exception:
            pass
    return None


def _list_interpolant_smtcnf_paths(instance: str, K: int, pddef: int = 1) -> List[str]:
    root = os.path.join("ProofDoorBenchmark")
    if not os.path.isdir(root):
        return []
    base_dirs: List[str] = []
    for prefix in ("interpolant_as_cnfs_", "interpolants_as_cnfs_"):
        cand = os.path.join(root, f"{prefix}{int(pddef)}", str(int(K)))
        if os.path.isdir(cand):
            base_dirs.append(cand)
    if not base_dirs:
        return []

    token = f"{instance}.{int(K)}."
    out: List[str] = []
    for base_dir in base_dirs:
        for fn in sorted(os.listdir(base_dir)):
            if not fn.endswith(".smtcnf"):
                continue
            if not fn.startswith(token):
                continue
            path = os.path.join(base_dir, fn)
            if not os.path.exists(path) or os.path.getsize(path) == 0:
                continue
            out.append(path)
    return out


def _proofdoor_source_status(instance: str, K: int, pddef: int = 1) -> Tuple[bool, bool, List[str]]:
    """
    Return (has_any_matched_file, has_empty_file, nonempty_paths).
    """
    root = os.path.join("ProofDoorBenchmark")
    if not os.path.isdir(root):
        return False, False, []
    base_dirs: List[str] = []
    for prefix in ("interpolant_as_cnfs_", "interpolants_as_cnfs_"):
        cand = os.path.join(root, f"{prefix}{int(pddef)}", str(int(K)))
        if os.path.isdir(cand):
            base_dirs.append(cand)
    if not base_dirs:
        return False, False, []

    token = f"{instance}.{int(K)}."
    has_any = False
    has_empty = False
    nonempty_paths: List[str] = []
    for base_dir in base_dirs:
        for fn in sorted(os.listdir(base_dir)):
            if not fn.endswith(".smtcnf"):
                continue
            if not fn.startswith(token):
                continue
            has_any = True
            path = os.path.join(base_dir, fn)
            if (not os.path.exists(path)) or os.path.getsize(path) == 0:
                has_empty = True
            else:
                nonempty_paths.append(path)
    return has_any, has_empty, nonempty_paths


def _should_skip_instance_due_to_empty_pds(instance: str, K: int, pddef: int = 1) -> bool:
    """
    Global datapoint filter: if any matched interpolant SMTCNF is empty, skip this datapoint.
    """
    _has_any, has_empty, _nonempty = _proofdoor_source_status(instance, K, pddef=pddef)
    return bool(has_empty)


def _compute_proofdoor_size_from_source(instance: str, K: int, pddef: int = 1) -> int:
    has_any, has_empty, matched_nonempty = _proofdoor_source_status(instance, K, pddef=pddef)
    if (not has_any) or has_empty or (not matched_nonempty):
        return 0
    try:
        return int(sum(theoretical_bits_smtcnf(p) for p in matched_nonempty))
    except Exception:
        return 0


def _load_info_row(instance: str, k: int) -> Dict[str, Any] | None:
    info_path = os.path.join("ProofDoorBenchmark", "cnfs", "info", f"{instance}.info.json")
    if not os.path.exists(info_path):
        return None
    try:
        with open(info_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None
    results = payload.get("results")
    if not isinstance(results, list):
        return None
    for row in results:
        try:
            if int(row["K"]) == int(k):
                return row
        except Exception:
            continue
    return None


def _compute_formula_size_from_cnf(instance: str, K: int) -> int:
    cnf_path = os.path.join(get_CNF_dir(int(K)), f"{instance}.{int(K)}.cnf")
    if not os.path.exists(cnf_path) or os.path.getsize(cnf_path) == 0:
        return 0
    try:
        return int(theoretical_bits_dimacs(cnf_path))
    except Exception:
        return 0


def _load_solving_time_from_info(instance: str, K: int) -> float | None:
    row = _load_info_row(instance, K)
    if not isinstance(row, dict):
        return None
    try:
        t = float(row["time"])
        return None if t < 0 else t
    except Exception:
        return None


def _build_pds_point_from_source(instance: str, K: int, pddef: int = 1) -> Dict[str, Any] | None:
    proofdoor_size = _compute_proofdoor_size_from_source(instance, K, pddef=pddef)
    if proofdoor_size <= 0:
        return None
    formula_size = _compute_formula_size_from_cnf(instance, K)
    solving_time = _load_solving_time_from_info(instance, K)
    if formula_size <= 0 or solving_time is None:
        return None
    return {
        "K": int(K),
        "formula_size": int(formula_size),
        "proofdoor_size": int(proofdoor_size),
        "y_value": float(solving_time),
    }


def _ensure_cached_proofdoor_size(
    pds_points: Dict[Tuple[str, int], Dict],
    instance: str,
    K: int,
    read_pds_from_source: bool = False,
    pddef: int = 1,
) -> Dict | None:
    key = (instance, int(K))
    p = pds_points.get(key)
    if read_pds_from_source and p is not None:
        has_any, has_empty, _ = _proofdoor_source_status(instance, int(K), pddef=pddef)
        # If source exists for this instance, source is authoritative under strict rules.
        if has_any:
            repaired = 0 if has_empty else _compute_proofdoor_size_from_source(instance, K, pddef=pddef)
            p["proofdoor_size"] = int(repaired) if repaired > 0 else 0
            return p
    if p is None:
        if not read_pds_from_source:
            return None
        built = _build_pds_point_from_source(instance, K, pddef=pddef)
        if built is None:
            return None
        pds_points[key] = built
        return built
    proofdoor_size = _parse_int(p.get("proofdoor_size"))
    if proofdoor_size is not None and proofdoor_size > 0:
        return p
    if not read_pds_from_source:
        return p
    built = _build_pds_point_from_source(instance, K, pddef=pddef)
    if built is not None:
        p.update(built)
    else:
        repaired = _compute_proofdoor_size_from_source(instance, K, pddef=pddef)
        if repaired > 0:
            p["proofdoor_size"] = int(repaired)
    return p


def _load_running_info(instance: str, k: int) -> Tuple[int, int, int]:
    info_path = os.path.join("ProofDoorBenchmark", "cnfs", "info", f"{instance}.info.json")
    with open(info_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    for r in payload["results"]:
        if int(r["K"]) == int(k):
            return int(r["m"]), int(r["n"]), int(r["proofsize"])
    raise KeyError(f"Missing K={k} in {info_path}")

def list_instances_from_aigs() -> List[str]:
    return sorted(
        os.path.splitext(fn)[0]
        for fn in os.listdir(get_aiger_dir())
        if fn.endswith(".aig")
    )


def _print_instances(prefix: str, instances: List[str]) -> None:
    print(f"--prefix={prefix}: {len(instances)} instances")
    for inst in instances:
        print(inst)


def _sorted_instances_by_x(insts: List[str], xs: List[float]) -> List[str]:
    pairs = sorted(zip(xs, insts), key=lambda t: (t[0], t[1]))
    return [inst for _, inst in pairs]


def _print_spd_instance_groups_by_x(
    out_path: str,
    found_instances: List[str],
    missing_instances: List[str],
) -> None:
    out = out_path or "<show>"
    print(f"spd_found_instances({len(found_instances)}) out={out}")
    print(json.dumps(found_instances, ensure_ascii=False))
    print("---")
    print(f"spd_missing_instances({len(missing_instances)}) out={out}")
    print(json.dumps(missing_instances, ensure_ascii=False))


def _candidate_prefixes(inst: str) -> List[str]:
    """
    Generate "human-ish" prefix candidates for --autoprefix.

    Candidates are created at:
      - delimiter boundaries ('-', '_', '.'): include the delimiter (e.g. "zipcpu-")
      - alpha->digit boundaries: exclude the digit (e.g. "139442p0" -> "139442p")
    """
    out: set[str] = set()
    for i, ch in enumerate(inst):
        if ch in "-_.":
            if i >= 0:
                out.add(inst[: i + 1])
    for i in range(1, len(inst)):
        if inst[i - 1].isalpha() and inst[i].isdigit():
            out.add(inst[:i])
    out.discard("")
    return sorted(out, key=len)


def _autoprefix_groups(instances: List[str], min_count: int) -> Dict[str, List[str]]:
    """
    Build groups for every qualifying prefix (overlap allowed).
    A prefix qualifies if it appears as a candidate in > min_count instances.
    Group membership is then computed by startswith(prefix), so a broader prefix
    (e.g. "bob") naturally includes narrower families (e.g. "bobtuint*").
    """
    cands_by_inst: Dict[str, List[str]] = {inst: _candidate_prefixes(inst) for inst in instances}
    counts: Dict[str, int] = {}
    for inst, cands in cands_by_inst.items():
        for pfx in cands:
            counts[pfx] = counts.get(pfx, 0) + 1

    qualifying = {pfx for pfx, c in counts.items() if int(c) > int(min_count)}
    groups: Dict[str, List[str]] = {
        pfx: sorted(inst for inst in instances if inst.startswith(pfx))
        for pfx in qualifying
    }
    groups = {pfx: xs for pfx, xs in groups.items() if len(xs) > int(min_count)}
    return dict(sorted(groups.items(), key=lambda kv: (len(kv[1]), kv[0]), reverse=True))


def _sanitize_for_filename(s: str, max_len: int = 80) -> str:
    safe = "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in s).strip("._-")
    if not safe:
        safe = "prefix"
    if len(safe) > max_len:
        h = hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]
        safe = f"{safe[:max_len]}_{h}"
    return safe


def _infer_instances_from_pds(K: int) -> List[str]:
    pds_json = _find_pds_scaling_results_json(K)
    _, pds_points = _load_pds_scaling_points(pds_json)
    return sorted({inst for (inst, kk) in pds_points.keys() if kk == int(K)})

def _scan_spd_available_instances(K: int, pddef: int) -> set[str]:
    """
    Scan `ProofDoorBenchmark/interpolant(s)_as_cnfs_<pddef>/<K>/` for `*.smtcnf` and return the set of
    instance names that have at least one corresponding file.
    """
    root = os.path.join("ProofDoorBenchmark")
    if not os.path.isdir(root):
        return set()
    base_dirs: List[str] = []
    for prefix in ("interpolant_as_cnfs_", "interpolants_as_cnfs_"):
        cand = os.path.join(root, f"{prefix}{int(pddef)}", str(int(K)))
        if os.path.isdir(cand):
            base_dirs.append(cand)
    if not base_dirs:
        return set()

    has_nonempty: set[str] = set()
    has_empty: set[str] = set()
    token = f".{int(K)}."
    for base_dir in base_dirs:
        for fn in os.listdir(base_dir):
            if not fn.endswith(".smtcnf"):
                continue
            if token not in fn:
                continue
            inst = fn.split(token, 1)[0]
            if inst:
                path = os.path.join(base_dir, fn)
                if (not os.path.exists(path)) or os.path.getsize(path) == 0:
                    has_empty.add(inst)
                else:
                    has_nonempty.add(inst)
    return {inst for inst in has_nonempty if inst not in has_empty}


@dataclass
class LinearRegressionResult:
    n: int
    slope: float
    intercept: float
    r2: float


def _linear_regression(xs: List[float], ys: List[float]) -> LinearRegressionResult | None:
    if len(xs) < 2:
        return None
    xf = np.asarray(xs, dtype=float)
    yf = np.asarray(ys, dtype=float)
    m, b = np.polyfit(xf, yf, 1)
    yhat = m * xf + b
    ss_res = float(np.sum((yf - yhat) ** 2))
    ss_tot = float(np.sum((yf - float(np.mean(yf))) ** 2))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
    return LinearRegressionResult(n=int(len(xs)), slope=float(m), intercept=float(b), r2=float(r2))


def _collect_xy_from_datapoints(
    data_points: List["DataPoint"],
    x_feature: str,
    y_feature: str,
    logx: bool = False,
    logy: bool = False,
    logy_bias: float = 0.01,
    filter_x: float = 0.0,
    filter_y: float = 0.0,
    fixed_n: float | None = None,
    nerror: float = 0.0,
) -> Tuple[List[float], List[float]]:
    xs: List[float] = []
    ys: List[float] = []
    n_lo = float(fixed_n - nerror) if fixed_n is not None else None
    n_hi = float(fixed_n + nerror) if fixed_n is not None else None
    for p in data_points:
        if n_lo is not None and n_hi is not None:
            nval = float(getattr(p, "ncnfvariables"))
            if nval < n_lo or nval > n_hi:
                continue
        xv = float(getattr(p, x_feature))
        yv = float(getattr(p, y_feature))
        if logx and xv <= 0:
            continue
        if logy and (yv + float(logy_bias)) <= 0:
            continue
        xs.append(xv)
        ys.append(yv)
    xs, ys = _trim_percent(xs, ys, float(filter_x), float(filter_y))
    return xs, ys


def _collect_xy_any_features(
    K: int,
    instances: List[str],
    x_feature: str,
    y_feature: str,
    logx: bool = False,
    logy: bool = False,
    logy_bias: float = 0.01,
    filter_x: float = 0.0,
    filter_y: float = 0.0,
    external: Dict[Tuple[str, int], Dict[str, float]] | None = None,
    read_pds_from_source: bool = False,
    fixed_n: float | None = None,
    nerror: float = 0.0,
) -> Tuple[str, str, List[float], List[float]]:
    aliases = {
        "time": "solving_time",
        "n": "ncnfvariables",
        "m": "nclauses",
        "proofsize": "proof_size",
        "pgs": "proofgate_size",
        "proofgate": "proofgate_size",
    }
    x_feature = aliases.get(x_feature, x_feature)
    y_feature = aliases.get(y_feature, y_feature)

    need_pds = (x_feature in PDS_FIELDS) or (y_feature in PDS_FIELDS)
    strict_pds = bool(read_pds_from_source) or (x_feature == "proofdoor_size") or (y_feature == "proofdoor_size")
    need_pgs = (x_feature in PGS_FIELDS) or (y_feature in PGS_FIELDS)
    strict_pgs = bool(read_pds_from_source) or (x_feature == "proofgate_size") or (y_feature == "proofgate_size")

    need_circuit = (x_feature in CIRCUIT_FIELDS) or (y_feature in CIRCUIT_FIELDS)
    need_run = (x_feature in RUN_FIELDS) or (y_feature in RUN_FIELDS)

    pds_points: Dict[Tuple[str, int], Dict] = {}
    if need_pds:
        pds_json = _find_pds_scaling_results_json(K)
        _, pds_points = _load_pds_scaling_points(pds_json)

    pgs_points: Dict[Tuple[str, int], Dict] = {}
    if need_pgs:
        try:
            pgs_json = _find_pds_scaling_results_json_by_pddef(
                K,
                pddef=3,
                preferred_tokens=["_ypgs_", "_ypgsdfs_", "_ypds_pddef3_"],
            )
            _, pgs_points = _load_pds_scaling_points(pgs_json)
        except Exception:
            pgs_points = {}

    circuit_features: Dict[str, Dict[str, int]] = {}
    if need_circuit:
        circuit_features = _read_circuit_features(get_circuit_features_dir())

    def _run_value(inst: str, feat: str) -> Any:
        if external is not None:
            e = external.get((inst, int(K)))
            if e is None:
                return None
            if feat == "nclauses" and "m" in e:
                return float(e["m"])
            if feat == "ncnfvariables" and "n" in e:
                return float(e["n"])
            if feat == "proof_size" and "proofsize" in e:
                return float(e["proofsize"])
            if feat == "solving_time" and "time" in e:
                t = float(e["time"])
                return None if t < 0 else t

        info_path = os.path.join("ProofDoorBenchmark", "cnfs", "info", f"{inst}.info.json")
        if not os.path.exists(info_path):
            return None
        with open(info_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        row = None
        for r in payload["results"]:
            if int(r["K"]) == int(K):
                row = r
                break
        if row is None:
            return None
        if feat == "nclauses":
            return int(row["m"])
        if feat == "ncnfvariables":
            return int(row["n"])
        if feat == "proof_size":
            return int(row["proofsize"])
        if feat == "solving_time":
            t = float(row["time"])
            return None if t < 0 else t
        return None

    def _value(inst: str, feat: str) -> Any:
        if feat == "K":
            return int(K)
        if feat in PDS_FIELDS:
            if feat == "solving_time":
                p = pds_points.get((inst, int(K)))
                if p is not None:
                    t = float(p["y_value"])
                    return None if t < 0 else t
                return _run_value(inst, "solving_time")
            p = _ensure_cached_proofdoor_size(
                pds_points,
                inst,
                int(K),
                read_pds_from_source=strict_pds,
            ) if feat == "proofdoor_size" else pds_points.get((inst, int(K)))
            if p is None:
                return None
            return p[feat]
        if feat in PGS_FIELDS:
            p = _ensure_cached_proofdoor_size(
                pgs_points,
                inst,
                int(K),
                read_pds_from_source=strict_pgs,
                pddef=3,
            )
            if p is None:
                return None
            pg = _parse_int(p.get("proofdoor_size"))
            return None if pg is None else int(pg)
        if feat in CIRCUIT_FIELDS:
            m = circuit_features.get(inst)
            if m is None:
                return None
            return m[feat]
        if feat in RUN_FIELDS:
            return _run_value(inst, feat)
        raise ValueError(f"Unknown feature: {feat}")

    xs: List[float] = []
    ys: List[float] = []
    n_lo = float(fixed_n - nerror) if fixed_n is not None else None
    n_hi = float(fixed_n + nerror) if fixed_n is not None else None
    for inst in instances:
        if need_pds and _should_skip_instance_due_to_empty_pds(inst, int(K), pddef=1):
            continue
        if need_pgs and _should_skip_instance_due_to_empty_pds(inst, int(K), pddef=3):
            continue
        if n_lo is not None and n_hi is not None:
            nval = _value(inst, "ncnfvariables")
            if nval is None:
                continue
            nval = float(nval)
            if nval < n_lo or nval > n_hi:
                continue
        xv = _value(inst, x_feature)
        yv = _value(inst, y_feature)
        if xv is None or yv is None:
            continue
        xv = float(xv)
        yv = float(yv)
        # proofdoor_size<=0 means missing/failed PDS and should be excluded.
        if x_feature == "proofdoor_size" and xv <= 0:
            continue
        if y_feature == "proofdoor_size" and yv <= 0:
            continue
        if x_feature == "proofgate_size" and xv <= 0:
            continue
        if y_feature == "proofgate_size" and yv <= 0:
            continue
        if logx and xv <= 0:
            continue
        if logy and (yv + float(logy_bias)) <= 0:
            continue
        xs.append(xv)
        ys.append(yv)

    xs, ys = _trim_percent(xs, ys, float(filter_x), float(filter_y))
    return x_feature, y_feature, xs, ys


def read_external_solving_points(path: str) -> Dict[Tuple[str, int], Dict[str, float]]:
    out: Dict[Tuple[str, int], Dict[str, float]] = {}
    with open(path, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            name = row["name"].strip()
            k = int(float(row["k"]))
            d: Dict[str, float] = {"time": float(row["time"])}
            if row.get("n", "").strip() != "":
                d["n"] = float(row["n"])
            if row.get("m", "").strip() != "":
                d["m"] = float(row["m"])
            if row.get("proofsize", "").strip() != "":
                d["proofsize"] = float(row["proofsize"])
            out[(name, k)] = d
    return out


def _trim_percent(xs: List[float], ys: List[float], fx: float, fy: float) -> Tuple[List[float], List[float]]:
    if not xs:
        return xs, ys
    keep = np.ones(len(xs), dtype=bool)
    if fx > 0.0:
        lo, hi = np.percentile(xs, [fx, 100.0 - fx])
        keep &= (np.asarray(xs) >= lo) & (np.asarray(xs) <= hi)
    if fy > 0.0:
        lo, hi = np.percentile(ys, [fy, 100.0 - fy])
        keep &= (np.asarray(ys) >= lo) & (np.asarray(ys) <= hi)
    idx = np.nonzero(keep)[0].tolist()
    return [xs[i] for i in idx], [ys[i] for i in idx]

def _trim_percent_idx(xs: List[float], ys: List[float], fx: float, fy: float) -> List[int]:
    if not xs:
        return []
    keep = np.ones(len(xs), dtype=bool)
    if fx > 0.0:
        lo, hi = np.percentile(xs, [fx, 100.0 - fx])
        keep &= (np.asarray(xs) >= lo) & (np.asarray(xs) <= hi)
    if fy > 0.0:
        lo, hi = np.percentile(ys, [fy, 100.0 - fy])
        keep &= (np.asarray(ys) >= lo) & (np.asarray(ys) <= hi)
    return np.nonzero(keep)[0].tolist()


def extract_aiger_features():
    """
    Extract simple structural features from all AIGER files in `get_aiger_dir()`.

    Output CSV schema: instance_name,nlatches,nands,noutputs,depth
    """

    def _read_aiger_latch_count(file_path: str) -> int:
        # AIGER header (both ascii and binary) starts with:
        #   "aag M I L O A" or "aig M I L O A"
        with open(file_path, "rb") as f:
            header = f.readline().decode("ascii", errors="strict").strip()
        parts = header.split()
        if len(parts) < 6 or parts[0] not in ("aig", "aag"):
            raise ValueError(f"Not an AIGER file (bad header): {file_path}")
        return int(parts[3])

    aiger_dir = get_aiger_dir()
    circuit_features: Dict[str, Dict[str, int]] = {}

    for fname in tqdm(sorted(os.listdir(aiger_dir))):
        if not fname.endswith(".aig"):
            continue

        path = os.path.join(aiger_dir, fname)
        instance = os.path.splitext(fname)[0]

        nlatches = _read_aiger_latch_count(path)
        if nlatches > 0:
            ntk = read_aiger_into_sequential_aig(path)
        else:
            ntk = read_aiger_into_aig(path)

        nands = int(ntk.num_gates())
        noutputs = int(ntk.num_pos())
        depth = int(DepthAig(ntk).num_levels())

        circuit_features[instance] = {
            "nlatches": nlatches,
            "nands": nands,
            "noutputs": noutputs,
            "depth": depth,
        }

    circuit_features_path = get_circuit_features_dir()
    os.makedirs(os.path.dirname(circuit_features_path) or ".", exist_ok=True)
    with open(circuit_features_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["instance_name", "nlatches", "nands", "noutputs", "depth"])
        for inst in sorted(circuit_features.keys()):
            feats = circuit_features[inst]
            w.writerow([inst, feats["nlatches"], feats["nands"], feats["noutputs"], feats["depth"]])

    return circuit_features


@dataclass
class DataPoint:
    source: str
    instance: str
    K: int
    formula_size: int
    proofdoor_size: int
    proof_size: int
    solving_time: float
    nlatches: int
    nands: int
    noutputs: int
    depth: int
    nclauses: int
    ncnfvariables: int

def load_data_points(
    K: int,
    instances: List[str],
    prefix: str = "",
    read_pds_from_source: bool = False,
) -> List[DataPoint]:
    # load circuit features
    circuit_features_path = get_circuit_features_dir()
    circuit_features = _read_circuit_features(circuit_features_path)

    # load pds_scaling_results (formula_size/proofdoor_size/solvingtime)
    pds_json = _find_pds_scaling_results_json(K)
    source_path, pds_points = _load_pds_scaling_points(pds_json)

    # infer instance list if not provided
    inferred_instances = not instances
    if not instances:
        instances = sorted({inst for (inst, kk) in pds_points.keys() if kk == int(K)})
        if prefix:
            instances = [inst for inst in instances if inst.startswith(prefix)]
            _print_instances(prefix, instances)

    data_points: List[DataPoint] = []
    missing_pds = 0
    missing_features = 0
    for inst in instances:
        if _should_skip_instance_due_to_empty_pds(inst, int(K)):
            continue
        key = (inst, int(K))
        if key not in pds_points:
            missing_pds += 1
            continue
        if inst not in circuit_features:
            missing_features += 1
            continue
        p = _ensure_cached_proofdoor_size(
            pds_points,
            inst,
            int(K),
            read_pds_from_source=read_pds_from_source,
        )
        if p is None:
            missing_pds += 1
            continue
        formula_size = int(p["formula_size"])
        proofdoor_size = int(_parse_int(p.get("proofdoor_size")) or 0)
        if proofdoor_size <= 0:
            missing_pds += 1
            continue
        solving_time = float(p["y_value"])
        if solving_time < 0:
            continue

        feats = circuit_features[inst]
        nlatches = int(feats["nlatches"])
        nands = int(feats["nands"])
        noutputs = int(feats["noutputs"])
        depth = int(feats["depth"])

        # load running_results (CNF size: clauses/vars + proofsize)
        nclauses, nvars, proof_size = _load_running_info(inst, int(K))

        data_points.append(
            DataPoint(
                source=source_path,
                instance=inst,
                K=int(K),
                formula_size=formula_size,
                proofdoor_size=proofdoor_size,
                proof_size=proof_size,
                solving_time=solving_time,
                nlatches=nlatches,
                nands=nands,
                noutputs=noutputs,
                depth=depth,
                nclauses=int(nclauses),
                ncnfvariables=int(nvars),
            )
        )

    print(
        f"load_data_points: requested={len(instances)} loaded={len(data_points)} "
        f"missing_pds={missing_pds} missing_features={missing_features}"
    )
    return data_points


def scatter_from_datapoints(
    data_points: List[DataPoint],
    x_feature: str,
    y_feature: str,
    out_path: str = "",
    title: str = "",
    alpha: float = 0.6,
    size: float = 12.0,
    logx: bool = False,
    logy: bool = False,
    logy_bias: float = 0.01,
    filter_x: float = 0.0,
    filter_y: float = 0.0,
    fit: str = "none",
    spd_available: set[str] | None = None,
    pd_visible: bool = False,
    fixed_n: float | None = None,
    nerror: float = 0.0,
    instance_labels: Dict[str, str] | None = None,
) -> None:
    insts: List[str] = []
    xs: List[float] = []
    ys: List[float] = []
    pds_raw: List[float] = []
    n_lo = float(fixed_n - nerror) if fixed_n is not None else None
    n_hi = float(fixed_n + nerror) if fixed_n is not None else None
    for p in data_points:
        if n_lo is not None and n_hi is not None:
            nval = float(getattr(p, "ncnfvariables"))
            if nval < n_lo or nval > n_hi:
                continue
        xv = float(getattr(p, x_feature))
        yv = float(getattr(p, y_feature))
        if logx and xv <= 0:
            continue
        if logy and (yv + float(logy_bias)) <= 0:
            continue
        insts.append(str(p.instance))
        xs.append(xv)
        ys.append(yv)
        pds_raw.append(float(getattr(p, "proofdoor_size", 0.0)))

    idx = _trim_percent_idx(xs, ys, float(filter_x), float(filter_y))
    insts = [insts[i] for i in idx]
    xs = [xs[i] for i in idx]
    ys = [ys[i] for i in idx]
    pds = [pds_raw[i] for i in idx]
    if xs:
        print(
            f"scatter: used={len(xs)} x_range=[{float(min(xs))}, {float(max(xs))}] "
            f"y_range=[{float(min(ys))}, {float(max(ys))}] (x={x_feature}, y={y_feature})"
        )
    plt.figure(figsize=(7, 5))
    ax = plt.gca()
    bias = float(logy_bias)
    spd_missing_instances: List[str] | None = None
    spd_found_instances: List[str] | None = None
    y_plot_all = [math.log10(y + bias) for y in ys] if logy else ys
    pd_axis_limits: Tuple[float, float] | None = None
    if instance_labels:
        _scatter_colored_by_labels(
            ax,
            insts,
            xs,
            y_plot_all,
            instance_labels,
            size=size,
            alpha=alpha,
            spd_available=spd_available,
        )
    elif spd_available is not None:
        xs_ok: List[float] = []
        ys_ok: List[float] = []
        xs_spd: List[float] = []
        ys_spd: List[float] = []
        spd_missing_instances = []
        spd_found_instances = []
        for inst, x, y in zip(insts, xs, ys):
            if inst in spd_available:
                xs_spd.append(x)
                ys_spd.append(y)
                spd_found_instances.append(inst)
            else:
                xs_ok.append(x)
                ys_ok.append(y)
                spd_missing_instances.append(inst)
        y_ok = [math.log10(y + bias) for y in ys_ok] if logy else ys_ok
        y_spd = [math.log10(y + bias) for y in ys_spd] if logy else ys_spd
        if xs_ok:
            ax.scatter(xs_ok, y_ok, s=size, alpha=alpha)
        if xs_spd:
            ax.scatter(xs_spd, y_spd, s=size, alpha=alpha, c="orange")
    else:
        y_plot = [math.log10(y + bias) for y in ys] if logy else ys
        ax.scatter(xs, y_plot, s=size, alpha=alpha)

    if pd_visible and spd_available is not None and xs:
        xs_pd: List[float] = []
        ys_pd: List[float] = []
        for inst, x, pd in zip(insts, xs, pds):
            if inst in spd_available and pd > 0:
                xs_pd.append(x)
                ys_pd.append(pd)
        if xs_pd:
            xy_sorted = sorted(zip(xs_pd, ys_pd), key=lambda t: t[0])
            xs_pd = [t[0] for t in xy_sorted]
            ys_pd = [t[1] for t in xy_sorted]
            ax2 = ax.twinx()
            ax2.plot(xs_pd, ys_pd, color="lightcoral", linewidth=1.5, alpha=0.8)
            ax2.set_ylabel("proofdoor_size")
            pd_axis_limits = (float(min(ys_pd)), float(max(ys_pd)))

    if fit != "none":
        xf = np.asarray(xs, dtype=float)
        yf = np.asarray(ys, dtype=float)
        xgrid = np.linspace(float(xf.min()), float(xf.max()), 300)
        if fit in ("linear", "both"):
            m, b = np.polyfit(xf, yf, 1)
            yhat = m * xgrid + b
            if logy:
                keep = (yhat + bias) > 0
                xplot = xgrid[keep]
                yplot = np.log10(yhat[keep] + bias)
            else:
                xplot = xgrid
                yplot = yhat
            plt.plot(xplot, yplot, linewidth=2, label=f"linear: y={m:.3g}x+{b:.3g}")
        if fit in ("exp", "both"):
            pos = yf > 0
            xf2 = xf[pos]
            yf2 = yf[pos]
            if xf2.size >= 2:
                B, lnA = np.polyfit(xf2, np.log(yf2), 1)
                A = float(np.exp(lnA))
                yhat = A * np.exp(B * xgrid)
                if logy:
                    keep = (yhat + bias) > 0
                    xplot = xgrid[keep]
                    yplot = np.log10(yhat[keep] + bias)
                else:
                    xplot = xgrid
                    yplot = yhat
                plt.plot(xplot, yplot, linewidth=2, label=f"exp: y={A:.3g}e^({B:.3g}x)")
        plt.legend()
    elif instance_labels:
        ax.legend(loc="best", fontsize=8)

    ax.set_xlabel(x_feature)
    ax.set_ylabel(f"log10({y_feature}+{bias:g})" if logy else y_feature)
    if logx:
        ax.set_xscale("log")
    if xs:
        ax.set_xlim(left=float(min(xs)))
    if y_plot_all:
        ax.set_ylim(bottom=float(min(y_plot_all)))
    if pd_axis_limits is not None:
        ax2 = ax.figure.axes[-1]
        ax2.set_ylim(bottom=pd_axis_limits[0])
    if title:
        plt.title(title)
    plt.tight_layout()
    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        plt.savefig(out_path, dpi=200)
    else:
        plt.show()

    if spd_missing_instances is not None and spd_found_instances is not None:
        missing_sorted = _sorted_instances_by_x(
            [inst for inst in insts if inst not in spd_available],
            [x for inst, x in zip(insts, xs) if inst not in spd_available],
        )
        found_sorted = _sorted_instances_by_x(
            [inst for inst in insts if inst in spd_available],
            [x for inst, x in zip(insts, xs) if inst in spd_available],
        )
        _print_spd_instance_groups_by_x(out_path, found_sorted, missing_sorted)

PDS_FIELDS = {"formula_size", "proofdoor_size", "solving_time"}
PGS_FIELDS = {"proofgate_size"}
CIRCUIT_FIELDS = {"nlatches", "nands", "noutputs", "depth"}
RUN_FIELDS = {"nclauses", "ncnfvariables", "proof_size"}


def scatter_any_features(
    K: int,
    instances: List[str],
    x_feature: str,
    y_feature: str,
    out_path: str = "",
    title: str = "",
    alpha: float = 0.6,
    size: float = 12.0,
    logx: bool = False,
    logy: bool = False,
    logy_bias: float = 0.01,
    filter_x: float = 0.0,
    filter_y: float = 0.0,
    fit: str = "none",
    external: Dict[Tuple[str, int], Dict[str, float]] | None = None,
    spd_available: set[str] | None = None,
    read_pds_from_source: bool = False,
    pd_visible: bool = False,
    fixed_n: float | None = None,
    nerror: float = 0.0,
    instance_labels: Dict[str, str] | None = None,
) -> None:
    aliases = {
        "time": "solving_time",
        "n": "ncnfvariables",
        "m": "nclauses",
        "proofsize": "proof_size",
        "pgs": "proofgate_size",
        "proofgate": "proofgate_size",
    }
    x_feature = aliases.get(x_feature, x_feature)
    y_feature = aliases.get(y_feature, y_feature)

    need_pds = (x_feature in PDS_FIELDS) or (y_feature in PDS_FIELDS)
    strict_pds = bool(read_pds_from_source) or (x_feature == "proofdoor_size") or (y_feature == "proofdoor_size")
    need_pgs = (x_feature in PGS_FIELDS) or (y_feature in PGS_FIELDS)
    strict_pgs = bool(read_pds_from_source) or (x_feature == "proofgate_size") or (y_feature == "proofgate_size")

    need_circuit = (x_feature in CIRCUIT_FIELDS) or (y_feature in CIRCUIT_FIELDS)
    need_run = (x_feature in RUN_FIELDS) or (y_feature in RUN_FIELDS)

    pds_points: Dict[Tuple[str, int], Dict] = {}
    if need_pds:
        pds_json = _find_pds_scaling_results_json(K)
        _, pds_points = _load_pds_scaling_points(pds_json)

    pgs_points: Dict[Tuple[str, int], Dict] = {}
    if need_pgs:
        try:
            pgs_json = _find_pds_scaling_results_json_by_pddef(
                K,
                pddef=3,
                preferred_tokens=["_ypgs_", "_ypgsdfs_", "_ypds_pddef3_"],
            )
            _, pgs_points = _load_pds_scaling_points(pgs_json)
        except Exception:
            pgs_points = {}

    circuit_features: Dict[str, Dict[str, int]] = {}
    if need_circuit:
        circuit_features = _read_circuit_features(get_circuit_features_dir())

    def _run_value(inst: str, feat: str) -> Any:
        if external is not None:
            e = external.get((inst, int(K)))
            if e is None:
                return None
            if feat == "nclauses" and "m" in e:
                return float(e["m"])
            if feat == "ncnfvariables" and "n" in e:
                return float(e["n"])
            if feat == "proof_size" and "proofsize" in e:
                return float(e["proofsize"])
            if feat == "solving_time" and "time" in e:
                t = float(e["time"])
                return None if t < 0 else t

        info_path = os.path.join("ProofDoorBenchmark", "cnfs", "info", f"{inst}.info.json")
        if not os.path.exists(info_path):
            return None
        with open(info_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        row = None
        for r in payload["results"]:
            if int(r["K"]) == int(K):
                row = r
                break
        if row is None:
            return None
        if feat == "nclauses":
            return int(row["m"])
        if feat == "ncnfvariables":
            return int(row["n"])
        if feat == "proof_size":
            return int(row["proofsize"])
        if feat == "solving_time":
            t = float(row["time"])
            return None if t < 0 else t
        return None

    def _value(inst: str, feat: str) -> Any:
        if feat == "K":
            return int(K)
        if feat in PDS_FIELDS:
            if feat == "solving_time":
                p = pds_points.get((inst, int(K)))
                if p is not None:
                    t = float(p["y_value"])
                    return None if t < 0 else t
                return _run_value(inst, "solving_time")
            p = _ensure_cached_proofdoor_size(
                pds_points,
                inst,
                int(K),
                read_pds_from_source=(strict_pds or bool(pd_visible)),
            ) if feat == "proofdoor_size" else pds_points.get((inst, int(K)))
            if p is None:
                return None
            return p[feat]
        if feat in PGS_FIELDS:
            p = _ensure_cached_proofdoor_size(
                pgs_points,
                inst,
                int(K),
                read_pds_from_source=(strict_pgs or bool(pd_visible)),
                pddef=3,
            )
            if p is None:
                return None
            pg = _parse_int(p.get("proofdoor_size"))
            return None if pg is None else int(pg)
        if feat in CIRCUIT_FIELDS:
            m = circuit_features.get(inst)
            if m is None:
                return None
            return m[feat]
        if feat in RUN_FIELDS:
            return _run_value(inst, feat)
        raise ValueError(f"Unknown feature: {feat}")

    insts_used: List[str] = []
    xs: List[float] = []
    ys: List[float] = []
    pds_raw: List[float] = []
    n_lo = float(fixed_n - nerror) if fixed_n is not None else None
    n_hi = float(fixed_n + nerror) if fixed_n is not None else None
    for inst in instances:
        if need_pds and _should_skip_instance_due_to_empty_pds(inst, int(K), pddef=1):
            continue
        if need_pgs and _should_skip_instance_due_to_empty_pds(inst, int(K), pddef=3):
            continue
        if n_lo is not None and n_hi is not None:
            nval = _value(inst, "ncnfvariables")
            if nval is None:
                continue
            nval = float(nval)
            if nval < n_lo or nval > n_hi:
                continue
        xv = _value(inst, x_feature)
        yv = _value(inst, y_feature)
        if xv is None or yv is None:
            continue
        xv = float(xv)
        yv = float(yv)
        # proofdoor_size<=0 means missing/failed PDS and should be excluded.
        if x_feature == "proofdoor_size" and xv <= 0:
            continue
        if y_feature == "proofdoor_size" and yv <= 0:
            continue
        if x_feature == "proofgate_size" and xv <= 0:
            continue
        if y_feature == "proofgate_size" and yv <= 0:
            continue
        if logx and xv <= 0:
            continue
        if logy and (yv + float(logy_bias)) <= 0:
            continue
        insts_used.append(str(inst))
        xs.append(xv)
        ys.append(yv)
        try:
            pd_val = _value(inst, "proofdoor_size")
            pds_raw.append(float(pd_val) if pd_val is not None else 0.0)
        except Exception:
            pds_raw.append(0.0)

    idx = _trim_percent_idx(xs, ys, float(filter_x), float(filter_y))
    insts_used = [insts_used[i] for i in idx]
    xs = [xs[i] for i in idx]
    ys = [ys[i] for i in idx]
    pds = [pds_raw[i] for i in idx]

    if xs:
        print(
            f"scatter: requested={len(instances)} used={len(xs)} "
            f"x_range=[{float(min(xs))}, {float(max(xs))}] "
            f"y_range=[{float(min(ys))}, {float(max(ys))}] (x={x_feature}, y={y_feature})"
        )
    plt.figure(figsize=(7, 5))
    ax = plt.gca()
    bias = float(logy_bias)
    spd_missing_instances: List[str] | None = None
    spd_found_instances: List[str] | None = None
    y_plot_all = [math.log10(y + bias) for y in ys] if logy else ys
    pd_axis_limits: Tuple[float, float] | None = None
    if instance_labels:
        _scatter_colored_by_labels(
            ax,
            insts_used,
            xs,
            y_plot_all,
            instance_labels,
            size=size,
            alpha=alpha,
            spd_available=spd_available,
        )
    elif spd_available is not None:
        xs_ok: List[float] = []
        ys_ok: List[float] = []
        xs_spd: List[float] = []
        ys_spd: List[float] = []
        spd_missing_instances = []
        spd_found_instances = []
        for inst, x, y in zip(insts_used, xs, ys):
            if inst in spd_available:
                xs_spd.append(x)
                ys_spd.append(y)
                spd_found_instances.append(inst)
            else:
                xs_ok.append(x)
                ys_ok.append(y)
                spd_missing_instances.append(inst)
        y_ok = [math.log10(y + bias) for y in ys_ok] if logy else ys_ok
        y_spd = [math.log10(y + bias) for y in ys_spd] if logy else ys_spd
        if xs_ok:
            ax.scatter(xs_ok, y_ok, s=size, alpha=alpha)
        if xs_spd:
            ax.scatter(xs_spd, y_spd, s=size, alpha=alpha, c="orange")
    else:
        y_plot = [math.log10(y + bias) for y in ys] if logy else ys
        ax.scatter(xs, y_plot, s=size, alpha=alpha)

    if pd_visible and spd_available is not None and xs:
        xs_pd: List[float] = []
        ys_pd: List[float] = []
        for inst, x, pd in zip(insts_used, xs, pds):
            if inst in spd_available and pd > 0:
                xs_pd.append(x)
                ys_pd.append(pd)
        print(f"pd_visible_line_points({len(xs_pd)}) out={out_path or '<show>'}")
        if xs_pd:
            xy_sorted = sorted(zip(xs_pd, ys_pd), key=lambda t: t[0])
            xs_pd = [t[0] for t in xy_sorted]
            ys_pd = [t[1] for t in xy_sorted]
            ax2 = ax.twinx()
            ax2.plot(xs_pd, ys_pd, color="lightcoral", linewidth=1.5, alpha=0.8)
            ax2.set_ylabel("proofdoor_size")
            pd_axis_limits = (float(min(ys_pd)), float(max(ys_pd)))

    if fit != "none":
        xf = np.asarray(xs, dtype=float)
        yf = np.asarray(ys, dtype=float)
        xgrid = np.linspace(float(xf.min()), float(xf.max()), 300)
        if fit in ("linear", "both"):
            m, b = np.polyfit(xf, yf, 1)
            yhat = m * xgrid + b
            if logy:
                keep = (yhat + bias) > 0
                xplot = xgrid[keep]
                yplot = np.log10(yhat[keep] + bias)
            else:
                xplot = xgrid
                yplot = yhat
            plt.plot(xplot, yplot, linewidth=2, label=f"linear: y={m:.3g}x+{b:.3g}")
        if fit in ("exp", "both"):
            pos = yf > 0
            xf2 = xf[pos]
            yf2 = yf[pos]
            if xf2.size >= 2:
                B, lnA = np.polyfit(xf2, np.log(yf2), 1)
                A = float(np.exp(lnA))
                yhat = A * np.exp(B * xgrid)
                if logy:
                    keep = (yhat + bias) > 0
                    xplot = xgrid[keep]
                    yplot = np.log10(yhat[keep] + bias)
                else:
                    xplot = xgrid
                    yplot = yhat
                plt.plot(xplot, yplot, linewidth=2, label=f"exp: y={A:.3g}e^({B:.3g}x)")
        plt.legend()
    elif instance_labels:
        ax.legend(loc="best", fontsize=8)

    ax.set_xlabel(x_feature)
    ax.set_ylabel(f"log10({y_feature}+{bias:g})" if logy else y_feature)
    if logx:
        ax.set_xscale("log")
    if xs:
        ax.set_xlim(left=float(min(xs)))
    if y_plot_all:
        ax.set_ylim(bottom=float(min(y_plot_all)))
    if pd_axis_limits is not None:
        ax2 = ax.figure.axes[-1]
        ax2.set_ylim(bottom=pd_axis_limits[0])
    if title:
        plt.title(title)
    plt.tight_layout()
    if out_path:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        plt.savefig(out_path, dpi=200)
    else:
        plt.show()

    if spd_missing_instances is not None and spd_found_instances is not None:
        missing_sorted = _sorted_instances_by_x(
            [inst for inst in insts_used if inst not in spd_available],
            [x for inst, x in zip(insts_used, xs) if inst not in spd_available],
        )
        found_sorted = _sorted_instances_by_x(
            [inst for inst in insts_used if inst in spd_available],
            [x for inst, x in zip(insts_used, xs) if inst in spd_available],
        )
        _print_spd_instance_groups_by_x(out_path, found_sorted, missing_sorted)


def read_instances_from_summary(summary_path: str, K: int) -> List[str]:
    with open(summary_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return sorted({row["instance_name"] for row in reader if int(row["K"]) == int(K)})


def read_instance_label_map(summary_path: str, K: int, column: str) -> Dict[str, str]:
    """Map instance_name -> label string for rows matching K (later rows overwrite)."""
    with open(summary_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or column not in reader.fieldnames:
            raise ValueError(
                f"summary CSV {summary_path!r} has no column {column!r}; "
                f"columns={list(reader.fieldnames or [])}"
            )
        out: Dict[str, str] = {}
        for row in reader:
            if int(row["K"]) != int(K):
                continue
            inst = str(row["instance_name"]).strip()
            raw = row.get(column, "")
            out[inst] = str(raw).strip() if raw is not None else ""
        return out


def _scatter_colored_by_labels(
    ax: Any,
    insts: List[str],
    xs: List[float],
    ys_plot: List[float],
    instance_labels: Dict[str, str],
    *,
    size: float,
    alpha: float,
    spd_available: Optional[set[str]],
) -> None:
    labels_eff = [
        (instance_labels.get(inst, "_no_label") or "_no_label").strip() or "_no_label" for inst in insts
    ]
    uniq = sorted(set(labels_eff))
    cmap = plt.get_cmap("tab10")
    for i, lab in enumerate(uniq):
        idxs = [j for j, ell in enumerate(labels_eff) if ell == lab]
        if not idxs:
            continue
        color = cmap(i % 10)
        xi = [xs[j] for j in idxs]
        yi = [ys_plot[j] for j in idxs]
        if spd_available is not None:
            edgecolors = ["orange" if insts[j] in spd_available else "none" for j in idxs]
            linewidths = [1.2 if insts[j] in spd_available else 0.0 for j in idxs]
            ax.scatter(
                xi,
                yi,
                s=size,
                alpha=alpha,
                color=color,
                edgecolors=edgecolors,
                linewidths=linewidths,
                label=lab,
            )
        else:
            ax.scatter(xi, yi, s=size, alpha=alpha, color=color, label=lab)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--K", type=int, default=10)
    parser.add_argument("--x", type=str, required=True)
    parser.add_argument("--y", type=str, required=True)
    parser.add_argument("--summary_path", type=str, default="")
    parser.add_argument(
        "--prefix",
        type=str,
        default="",
        help="Only keep instances whose name starts with this prefix.",
    )
    parser.add_argument(
        "--autoprefix",
        "--auto_prefix",
        type=int,
        default=0,
        help="If >0, automatically group instances by prefix and run one plot per prefix "
        "whose instance count is > this threshold. Outputs to figures/scalability/.",
    )
    parser.add_argument("--out", type=str, default="")
    parser.add_argument("--title", type=str, default="")
    parser.add_argument("--alpha", type=float, default=0.6)
    parser.add_argument("--size", type=float, default=12.0)
    parser.add_argument("--all", action="store_true", default=False)
    parser.add_argument("--logx", action="store_true", default=False)
    parser.add_argument("--logy", action="store_true", default=False)
    parser.add_argument("--logy-bias", type=float, default=0.01)
    parser.add_argument("--filter-x", "--filer-x", dest="filter_x", type=float, default=0.0)
    parser.add_argument("--filter-y", "--filer-y", dest="filter_y", type=float, default=0.0)
    parser.add_argument("--externalst", action="store_true", default=False)
    parser.add_argument("--externalst-path", type=str, default="../BMC-benchmark/results/solving_points.csv")
    parser.add_argument("--fit", type=str, default="none", choices=["none", "linear", "exp", "both"])
    parser.add_argument(
        "--color-label-column",
        type=str,
        default="",
        metavar="COL",
        help="With --summary_path, color scatter points by this CSV column (e.g. category). "
        "Uses rows matching --K. With --mark_spd_available, SPD instances get an orange edge.",
    )
    parser.add_argument(
        "--read_pds_from_source",
        action="store_true",
        default=False,
        help="If set, repair missing cached proofdoor_size values by rereading interpolant_as_cnfs_1/<K>/ and recomputing bits.",
    )
    parser.add_argument(
        "--mark_spd_available",
        type=int,
        default=-1,
        metavar="PDDEF",
        help="If >=0, color points orange when a matching *.smtcnf exists under "
        "ProofDoorBenchmark/interpolant_as_cnfs_PDDEF/<K>/ (or interpolants_as_cnfs_PDDEF/<K>/).",
    )
    parser.add_argument(
        "--pd_visible",
        action="store_true",
        default=False,
        help="When used with --mark_spd_available, add a secondary right y-axis "
        "showing proofdoor_size as a light red line for SPD-available instances.",
    )
    parser.add_argument(
        "--fixed_n",
        type=float,
        default=None,
        help="If set, keep only points with ncnfvariables in [fixed_n - nerror, fixed_n + nerror].",
    )
    parser.add_argument(
        "--nerror",
        type=float,
        default=0.0,
        help="Half-width of ncnfvariables filter interval used with --fixed_n.",
    )
    args = parser.parse_args()
    if float(args.nerror) < 0:
        parser.error("--nerror must be non-negative")

    arg_aliases = {
        "time": "solving_time",
        "n": "ncnfvariables",
        "m": "nclauses",
        "proofsize": "proof_size",
        "pgs": "proofgate_size",
        "proofgate": "proofgate_size",
    }
    x_norm = arg_aliases.get(str(args.x), str(args.x))
    y_norm = arg_aliases.get(str(args.y), str(args.y))
    use_any_features_path = bool(args.all) or (x_norm == "proofgate_size") or (y_norm == "proofgate_size")

    instances: List[str] = []
    # If summary_path is provided, it is the authoritative instance list.
    if args.summary_path:
        instances = read_instances_from_summary(args.summary_path, args.K)
    elif args.all or (args.externalst and not args.summary_path):
        instances = list_instances_from_aigs()

    external = read_external_solving_points(args.externalst_path) if args.externalst else None
    spd_available = (
        _scan_spd_available_instances(args.K, int(args.mark_spd_available))
        if int(args.mark_spd_available) >= 0
        else None
    )

    instance_labels: Dict[str, str] | None = None
    label_col = str(args.color_label_column).strip()
    if label_col:
        if not str(args.summary_path).strip():
            parser.error("--color-label-column requires --summary_path")
        try:
            instance_labels = read_instance_label_map(str(args.summary_path), int(args.K), label_col)
        except (ValueError, KeyError, OSError) as e:
            parser.error(str(e))

    # autoprefix mode: run one plot per detected prefix group
    if int(args.autoprefix) > 0:
        base_instances = instances or _infer_instances_from_pds(args.K)
        if args.prefix:
            base_instances = [inst for inst in base_instances if inst.startswith(str(args.prefix))]

        groups = _autoprefix_groups(base_instances, int(args.autoprefix))
        if not groups:
            print(f"--autoprefix={int(args.autoprefix)}: no prefixes found")
            return

        out_dir = os.path.join("figures", "scalability")
        os.makedirs(out_dir, exist_ok=True)
        lr_rows: List[Tuple[str, str, str, LinearRegressionResult | None, str]] = []
        for pfx, insts in groups.items():
            _print_instances(pfx, insts)
            safe = _sanitize_for_filename(pfx)
            h = hashlib.sha1(pfx.encode("utf-8")).hexdigest()[:8]
            out_path = os.path.join(out_dir, f"K{int(args.K)}_{str(args.x)}_{str(args.y)}_{safe}_{h}.png")
            title = str(args.title)
            if title:
                title = f"{title} [{pfx}]"

            # autoprefix: always run LR; plot shows at least the linear fit
            fit_for_plot = "both" if str(args.fit) == "both" else "linear"

            if use_any_features_path:
                xname, yname, xs_lr, ys_lr = _collect_xy_any_features(
                    args.K,
                    insts,
                    str(args.x),
                    str(args.y),
                    logx=bool(args.logx),
                    logy=bool(args.logy),
                    logy_bias=float(args.logy_bias),
                    filter_x=float(args.filter_x),
                    filter_y=float(args.filter_y),
                    external=external,
                    read_pds_from_source=bool(args.read_pds_from_source),
                    fixed_n=args.fixed_n,
                    nerror=float(args.nerror),
                )
                lr = _linear_regression(xs_lr, ys_lr)
                scatter_any_features(
                    args.K,
                    insts,
                    args.x,
                    args.y,
                    out_path=out_path,
                    title=title,
                    alpha=float(args.alpha),
                    size=float(args.size),
                    logx=bool(args.logx),
                    logy=bool(args.logy),
                    logy_bias=float(args.logy_bias),
                    filter_x=float(args.filter_x),
                    filter_y=float(args.filter_y),
                    fit=fit_for_plot,
                    external=external,
                    spd_available=spd_available,
                    read_pds_from_source=bool(args.read_pds_from_source),
                    pd_visible=bool(args.pd_visible),
                    fixed_n=args.fixed_n,
                    nerror=float(args.nerror),
                    instance_labels=instance_labels,
                )
            else:
                pts = load_data_points(args.K, insts, read_pds_from_source=bool(args.read_pds_from_source))
                xs_lr, ys_lr = _collect_xy_from_datapoints(
                    pts,
                    str(args.x),
                    str(args.y),
                    logx=bool(args.logx),
                    logy=bool(args.logy),
                    logy_bias=float(args.logy_bias),
                    filter_x=float(args.filter_x),
                    filter_y=float(args.filter_y),
                    fixed_n=args.fixed_n,
                    nerror=float(args.nerror),
                )
                lr = _linear_regression(xs_lr, ys_lr)
                scatter_from_datapoints(
                    pts,
                    args.x,
                    args.y,
                    out_path=out_path,
                    title=title,
                    alpha=float(args.alpha),
                    size=float(args.size),
                    logx=bool(args.logx),
                    logy=bool(args.logy),
                    logy_bias=float(args.logy_bias),
                    filter_x=float(args.filter_x),
                    filter_y=float(args.filter_y),
                    fit=fit_for_plot,
                    spd_available=spd_available,
                    pd_visible=bool(args.pd_visible),
                    fixed_n=args.fixed_n,
                    nerror=float(args.nerror),
                    instance_labels=instance_labels,
                )
                xname, yname = str(args.x), str(args.y)

            lr_rows.append((pfx, xname, yname, lr, out_path))

        print("=== autoprefix linear regression summary ===")
        for pfx, xname, yname, lr, out_path in lr_rows:
            if lr is None:
                print(f"LR[{pfx}] n<2 (skipped) x={xname} y={yname} out={out_path}")
            else:
                print(
                    f"LR[{pfx}] n={lr.n} x={xname} y={yname} slope={lr.slope:.6g} "
                    f"intercept={lr.intercept:.6g} R2={lr.r2:.6g} out={out_path}"
                )
        return

    if args.prefix:
        instances = [inst for inst in instances if inst.startswith(str(args.prefix))]
        if instances:
            _print_instances(str(args.prefix), instances)

    if use_any_features_path:
        scatter_any_features(
            args.K,
            instances,
            args.x,
            args.y,
            out_path=args.out,
            title=args.title,
            alpha=float(args.alpha),
            size=float(args.size),
            logx=bool(args.logx),
            logy=bool(args.logy),
            logy_bias=float(args.logy_bias),
            filter_x=float(args.filter_x),
            filter_y=float(args.filter_y),
            fit=str(args.fit),
            external=external,
            spd_available=spd_available,
            read_pds_from_source=bool(args.read_pds_from_source),
            pd_visible=bool(args.pd_visible),
            fixed_n=args.fixed_n,
            nerror=float(args.nerror),
            instance_labels=instance_labels,
        )
    else:
        pts = load_data_points(
            args.K,
            instances,
            prefix=str(args.prefix),
            read_pds_from_source=bool(args.read_pds_from_source),
        )
        scatter_from_datapoints(
            pts,
            args.x,
            args.y,
            out_path=args.out,
            title=args.title,
            alpha=float(args.alpha),
            size=float(args.size),
            logx=bool(args.logx),
            logy=bool(args.logy),
            logy_bias=float(args.logy_bias),
            filter_x=float(args.filter_x),
            filter_y=float(args.filter_y),
            fit=str(args.fit),
            spd_available=spd_available,
            pd_visible=bool(args.pd_visible),
            fixed_n=args.fixed_n,
            nerror=float(args.nerror),
            instance_labels=instance_labels,
        )


if __name__ == "__main__":
    main()

