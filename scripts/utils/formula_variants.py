import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional

from utils.paths import get_CNF_dir, get_scranfilized_CNF, get_scranfilized_meta
from utils.process_cnf import CNF
from utils.scramble import scramble_cnf


BOUNDARY_MODE_PHYSICAL = "physical"
SCRANFILIZE_PROFILES: Dict[str, List[str]] = {
    "clause_light": ["-f", "0", "-v", "0", "-c", "0.01"],
    "clause_mid": ["-f", "0", "-v", "0", "-c", "0.10"],
    "clause_full": ["-f", "0", "-v", "0", "-P"],
    "var_light": ["-f", "0", "-v", "0.01", "-c", "0"],
    "var_full": ["-f", "0", "-p", "-c", "0"],
    "all_light": ["-f", "0", "-v", "0.01", "-c", "0.01"],
}


@dataclass(frozen=True)
class FormulaVariant:
    permute: Optional[str] = None
    permute_index: int = 0
    scranfilize_profile: Optional[str] = None
    scranfilize_seed: int = 0
    boundary_mode: str = BOUNDARY_MODE_PHYSICAL

    def suffix(self) -> str:
        if self.scranfilize_profile:
            return f".scr_{self.scranfilize_profile}_s{self.scranfilize_seed}"
        if self.permute:
            return f".perm_{self.permute}_{self.permute_index}"
        return ""

    def title_suffix(self) -> str:
        return self.suffix().replace(".", "_")

    def cli_flags(self) -> str:
        parts: List[str] = []
        if self.permute:
            parts += ["--permute", self.permute, "--permute_index", str(self.permute_index)]
        if self.scranfilize_profile:
            parts += [
                "--scranfilize_profile",
                self.scranfilize_profile,
                "--scranfilize_seed",
                str(self.scranfilize_seed),
                "--boundary_mode",
                self.boundary_mode,
            ]
        return " ".join(parts)

    def validate(self) -> None:
        if self.permute and self.scranfilize_profile:
            raise ValueError("Use either --permute or --scranfilize_profile, not both")
        if self.scranfilize_profile:
            if self.scranfilize_profile not in SCRANFILIZE_PROFILES:
                raise ValueError(
                    f"Unknown scranfilize profile {self.scranfilize_profile!r}; "
                    f"choices: {sorted(SCRANFILIZE_PROFILES)}"
                )
            if self.boundary_mode != BOUNDARY_MODE_PHYSICAL:
                raise ValueError("Only boundary_mode=physical is currently implemented")


def make_formula_variant(
    *,
    permute: Optional[str] = None,
    permute_index: int = 0,
    scranfilize_profile: Optional[str] = None,
    scranfilize_seed: int = 0,
    boundary_mode: str = BOUNDARY_MODE_PHYSICAL,
) -> FormulaVariant:
    variant = FormulaVariant(
        permute=permute,
        permute_index=permute_index,
        scranfilize_profile=scranfilize_profile,
        scranfilize_seed=scranfilize_seed,
        boundary_mode=boundary_mode,
    )
    variant.validate()
    return variant


def add_variant_args(parser) -> None:
    parser.add_argument(
        "--scranfilize_profile",
        choices=sorted(SCRANFILIZE_PROFILES),
        default=None,
        help="Generate/use a scranfilize CNF variant profile",
    )
    parser.add_argument("--scranfilize_seed", type=int, default=0)
    parser.add_argument(
        "--boundary_mode",
        choices=[BOUNDARY_MODE_PHYSICAL],
        default=BOUNDARY_MODE_PHYSICAL,
        help="How to restore c iter comments after scranfilize",
    )


def get_original_cnf_path(name: str, K: int) -> str:
    return f"{get_CNF_dir(K)}/{name}.{K}.cnf"


def get_formula_cnf_path(name: str, K: int, variant: FormulaVariant) -> str:
    if variant.scranfilize_profile:
        return get_scranfilized_CNF(
            name,
            K,
            variant.scranfilize_profile,
            variant.scranfilize_seed,
        )
    if variant.permute:
        from utils.paths import get_scrambled_CNF

        return get_scrambled_CNF(name, K, variant.permute, variant.permute_index)
    return get_original_cnf_path(name, K)


def ensure_formula_variant_exists(name: str, K: int, variant: FormulaVariant) -> None:
    variant.validate()
    if not variant.permute and not variant.scranfilize_profile:
        return
    original = get_original_cnf_path(name, K)
    if not os.path.exists(original):
        raise FileNotFoundError(f"Original CNF not found: {original}")
    output = get_formula_cnf_path(name, K, variant)
    if os.path.exists(output) and os.path.getsize(output) > 0:
        return
    if variant.permute:
        scramble_cnf(original, output, variant.permute)
        return
    generate_scranfilized_cnf(name, K, variant)


def find_scranfilize_binary(explicit: Optional[str] = None) -> str:
    candidates: List[str] = []
    if explicit:
        candidates.append(explicit)
    env_path = os.environ.get("SCRANFILIZE")
    if env_path:
        candidates.append(env_path)
    candidates.extend(
        [
            "./External/scranfilize/scranfilize",
            "./External/scranfilize/build/scranfilize",
            "./scranfilize",
        ]
    )
    found = shutil.which("scranfilize")
    if found:
        candidates.append(found)
    for candidate in candidates:
        if candidate and os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError(
        "scranfilize binary not found. Set SCRANFILIZE=/path/to/scranfilize "
        "or place it at External/scranfilize/scranfilize."
    )


def iter_clause_counts(cnf: CNF) -> List[int]:
    iter_map = cnf.get_iter_map()
    if not iter_map:
        return [len(cnf.get_clauses())]
    keys = sorted(iter_map.keys())
    counts: List[int] = []
    for idx, iter_idx in enumerate(keys):
        start = iter_map[iter_idx]
        end = len(cnf.clauses) if idx + 1 == len(keys) else iter_map[keys[idx + 1]]
        count = end - start
        # process_cnf.CNF initializes iter_map[0] = 0 and also records a leading
        # "c iter 0" as the next key, which creates a synthetic empty block.
        if count > 0:
            counts.append(count)
    return counts


def apply_physical_iter_boundaries(scrambled: CNF, counts: List[int]) -> CNF:
    if sum(counts) != len(scrambled.clauses):
        raise ValueError(
            f"iteration clause counts sum to {sum(counts)}, "
            f"but scranfilize output has {len(scrambled.clauses)} clauses"
        )
    scrambled.iter_map = {}
    clause_index = 0
    for iter_idx, count in enumerate(counts):
        scrambled.iter_map[iter_idx] = clause_index
        clause_index += count
    scrambled.K = max(0, len(counts) - 1)
    return scrambled


def generate_scranfilized_cnf(
    name: str,
    K: int,
    variant: FormulaVariant,
    *,
    scranfilize_binary: Optional[str] = None,
) -> str:
    if not variant.scranfilize_profile:
        raise ValueError("generate_scranfilized_cnf requires scranfilize_profile")
    if variant.boundary_mode != BOUNDARY_MODE_PHYSICAL:
        raise ValueError("Only physical boundary restoration is implemented")

    original = get_original_cnf_path(name, K)
    output = get_formula_cnf_path(name, K, variant)
    meta_path = get_scranfilized_meta(
        name,
        K,
        variant.scranfilize_profile,
        variant.scranfilize_seed,
    )
    original_cnf = CNF(original, skip_parse_literal_map=True)
    counts = iter_clause_counts(original_cnf)
    binary = find_scranfilize_binary(scranfilize_binary)
    profile_args = SCRANFILIZE_PROFILES[variant.scranfilize_profile]
    cmd = [binary, "-s", str(variant.scranfilize_seed), *profile_args, original]

    with tempfile.NamedTemporaryFile(prefix="scranfilize-", suffix=".cnf", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        with open(tmp_path, "w") as tmp_out:
            subprocess.run(cmd, stdout=tmp_out, stderr=subprocess.PIPE, text=True, check=True)
        scrambled_cnf = CNF(tmp_path, skip_parse_literal_map=True)
        if scrambled_cnf.L != original_cnf.L:
            raise ValueError(f"variable count changed from {original_cnf.L} to {scrambled_cnf.L}")
        if len(scrambled_cnf.clauses) != len(original_cnf.clauses):
            raise ValueError(
                f"clause count changed from {len(original_cnf.clauses)} to {len(scrambled_cnf.clauses)}"
            )
        apply_physical_iter_boundaries(scrambled_cnf, counts).to_dimacs(output)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"scranfilize failed: {' '.join(cmd)}\n{exc.stderr}") from exc
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    meta = {
        "instance": name,
        "K": K,
        "profile": variant.scranfilize_profile,
        "seed": variant.scranfilize_seed,
        "scranfilize_args": cmd[1:-1],
        "boundary_mode": variant.boundary_mode,
        "orig_cnf": original,
        "scrambled_cnf": output,
        "orig_num_vars": original_cnf.L,
        "orig_num_clauses": len(original_cnf.clauses),
        "iter_clause_counts": counts,
    }
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
    return output
