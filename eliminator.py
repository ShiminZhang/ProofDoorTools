#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DP (Davis–Putnam) elimination for a specified set of existential variables on CNF.

Features:
  - Only eliminates user-specified variables (ELIM_VARS).
  - Pure DP resolution (CNF -> CNF).
  - Targeted propagation LIMITED to ELIM_VARS and LIMITED to clauses touching the current var (POS ∪ NEG).
  - Parallel resolvent generation with guards: max-new (count) and max-width (clause width).
  - Clause subsumption:
      * Use short resolvents (width ≤ SHORT_W) to delete strict supersets in REST (parallel, posting-list based).
      * Optional intra-RES subsumption (short→long) to keep RES minimal.
  - QDIMACS-safe parsing: ignores 'e ... 0' / 'a ... 0' prefix lines; preserves comments.

Recommended starting params for ~32 GB RAM:
  --max-new 3e6, --max-width 26, --workers 8..16,
  --up-rounds 1..2, --short-w 5, --cand-limit 5000, --del-limit 2e6
"""

import argparse
import multiprocessing as mp
import os
import sys
import time
from collections import defaultdict
from itertools import islice

# ----------------------------------------------------------------------
# I/O
# ----------------------------------------------------------------------

def parse_dimacs(path):
    comments = []
    clauses = []
    nvars = None
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            s = raw.strip()
            if not s:
                continue
            if s.startswith('c'):
                comments.append(s); continue
            if s.startswith('p'):
                ps = s.split()
                if len(ps) >= 4 and ps[1] == 'cnf':
                    nvars = int(ps[2])
                continue
            # Skip QDIMACS prefix lines entirely
            if s.startswith('e ') or s.startswith('a ') or s == 'e' or s == 'a':
                continue
            # Clause line: ints terminated by 0
            toks = s.split()
            lits = [int(x) for x in toks if x != '0']
            if not lits:
                clauses.append(tuple())  # empty clause
                continue
            st = set(lits)
            # Drop tautologies (contain l and -l)
            taut = any((-l in st) for l in st)
            if taut:
                continue
            clauses.append(tuple(sorted(st)))
    if nvars is None:
        mx = 0
        for c in clauses:
            for l in c:
                if abs(l) > mx:
                    mx = abs(l)
        nvars = mx
    return comments, nvars, clauses


def write_dimacs(path, comments, nvars, clauses):
    with open(path, "w", encoding="utf-8") as f:
        for c in comments:
            f.write(c + "\n")
        f.write(f"p cnf {nvars} {len(clauses)}\n")
        for c in clauses:
            if len(c) == 0:
                f.write("0\n")
            else:
                f.write(" ".join(map(str, c)) + " 0\n")


# ----------------------------------------------------------------------
# Utils
# ----------------------------------------------------------------------

def dedup_clauses(clauses):
    # Exact dedup via tuple hashing (order-preserving)
    return list(dict.fromkeys(clauses).keys())

def chunk_iter(it, size):
    it = iter(it)
    while True:
        chunk = list(islice(it, size))
        if not chunk:
            break
        yield chunk

# ----------------------------------------------------------------------
# Targeted propagation (ELIM_VARS only), scoped to POS ∪ NEG
# ----------------------------------------------------------------------

def targeted_up_elim_only(pos, neg, elim_vars, max_rounds=2):
    """
    Only propagate unit literals whose variable is in elim_vars.
    Scope limited to S = pos ∪ neg. Do not touch REST.
    Returns the updated list of clauses S (pos ∪ neg) after propagation.
    """
    if max_rounds <= 0:
        return list(pos) + list(neg)

    # Work on a flat list S
    S = list(pos) + list(neg)

    rounds = 0
    while rounds < max_rounds:
        # collect units that are in elim_vars
        units = []
        for c in S:
            if len(c) == 1:
                lit = c[0]
                if abs(lit) in elim_vars:
                    units.append(lit)
        if not units:
            break
        uset = set(units)

        newS = []
        for c in S:
            sc = set(c)
            # satisfied by a unit?
            if any(u in sc for u in uset):
                continue
            # remove negated units
            s2 = tuple(sorted(x for x in c if -x not in uset))
            # skip generated tautologies (not expected here)
            if any((-l in s2) for l in s2):
                continue
            newS.append(s2)
        S = newS
        rounds += 1

    # Re-partition handled by caller.
    return S


# ----------------------------------------------------------------------
# Resolution core (parallel)
# ----------------------------------------------------------------------

def make_resolvent(c1, c2, var, a_is_pos):
    """
    Resolve on var. If a_is_pos==True, c1 contains +var and c2 contains -var; otherwise reversed.
    Return tuple resolvent or None if tautology.
    """
    s1 = set(c1)
    s2 = set(c2)
    if a_is_pos:
        s1.discard(var)
        s2.discard(-var)
    else:
        s1.discard(-var)
        s2.discard(var)
    # tautology check: l ∈ s1 and -l ∈ s2
    for l in s1:
        if -l in s2:
            return None
    res = s1 | s2
    return tuple(sorted(res))

def _worker_resolve(args):
    a_chunk, b_all, var, a_is_pos, max_width = args
    out = []
    for c1 in a_chunk:
        len1 = len(c1) - 1
        for c2 in b_all:
            # quick width upper bound (without explicit resolvent build)
            target_w = len1 + (len(c2) - 1)
            if max_width > 0 and target_w > max_width:
                continue
            r = make_resolvent(c1, c2, var, a_is_pos)
            if r is None:
                continue
            if max_width > 0 and len(r) > max_width:
                continue
            out.append(r)
    return out

def parallel_resolvents(pos, neg, var, max_width, workers, max_new, abort_on_explode):
    """
    Generate resolvents between POS and NEG on var with guards.
    Returns (RES list, exploded: bool, skipped: bool)
    """
    if not pos or not neg:
        return [], False, False

    # choose smaller side to chunk
    a_is_pos = len(pos) <= len(neg)
    A = pos if a_is_pos else neg
    B = neg if a_is_pos else pos

    chunk_size = max(128, max(len(A) // ( (workers if workers>0 else 1) * 4 ), 128))

    resolvents = []
    if workers <= 1:
        for ch in chunk_iter(A, chunk_size):
            res = _worker_resolve((ch, B, var, a_is_pos, max_width))
            resolvents.extend(res)
            if max_new >= 0 and len(resolvents) > max_new:
                if abort_on_explode:
                    return [], True, False
                else:
                    return [], False, True
    else:
        with mp.Pool(processes=workers) as pool:
            futures = []
            for ch in chunk_iter(A, chunk_size):
                futures.append(pool.apply_async(_worker_resolve, ((ch, B, var, a_is_pos, max_width),)))
            for f in futures:
                res = f.get()
                resolvents.extend(res)
                if max_new >= 0 and len(resolvents) > max_new:
                    if abort_on_explode:
                        return [], True, False
                    else:
                        return [], False, True

    return dedup_clauses(resolvents), False, False


# ----------------------------------------------------------------------
# Subsumption (parallel, posting-list based)
# ----------------------------------------------------------------------

def build_inverted_index(clauses):
    """clauses: List[Tuple[int]] -> Dict[int, Set[int]]"""
    idx = defaultdict(set)
    for i, c in enumerate(clauses):
        for l in c:
            idx[l].add(i)
    return idx

def _subsumption_batch_worker(args):
    batch_shorts, idx, clauses, cand_limit = args
    killed = set()
    for s in batch_shorts:
        if not s:
            continue
        lits = list(s)
        # order by posting length ascending to tighten intersections faster
        lits.sort(key=lambda lit: len(idx.get(lit, ())) )
        # compute candidate ids that contain all lits
        if not lits:
            continue
        cand = idx.get(lits[0], set()).copy()
        for lit in lits[1:]:
            cand &= idx.get(lit, set())
            if not cand:
                break
        if not cand:
            continue
        # cap candidate size for safety
        if cand_limit > 0 and len(cand) > cand_limit:
            cand = set(islice(cand, cand_limit))
        s_set = set(s)
        for j in cand:
            if j in killed:
                continue
            cj = clauses[j]
            # strict superset only
            if len(cj) > len(s) and s_set.issubset(cj):
                killed.add(j)
    return killed

def subsume_by_shorts(target_clauses, short_clauses, workers=1, cand_limit=5000, del_limit=2_000_000):
    """
    Use short_clauses (width ≤ SHORT_W) to delete strict supersets in target_clauses.
    Returns (new_target_clauses, removed_count).
    """
    if not target_clauses or not short_clauses:
        return target_clauses, 0

    idx = build_inverted_index(target_clauses)

    shorts = list(short_clauses)
    batch_size = max(1024, len(shorts) // (3 * max(1, workers)))
    batches = []
    it = iter(shorts)
    while True:
        chunk = list(islice(it, batch_size))
        if not chunk:
            break
        batches.append(chunk)

    removed = set()
    if workers <= 1:
        for b in batches:
            k = _subsumption_batch_worker((b, idx, target_clauses, cand_limit))
            removed |= k
            if 0 < del_limit < len(removed):
                break
    else:
        with mp.Pool(processes=workers) as pool:
            futures = [pool.apply_async(_subsumption_batch_worker, ((b, idx, target_clauses, cand_limit),))
                       for b in batches]
            for f in futures:
                k = f.get()
                removed |= k
                if 0 < del_limit < len(removed):
                    break

    if not removed:
        return target_clauses, 0

    kept = [c for i, c in enumerate(target_clauses) if i not in removed]
    return kept, len(removed)

def subsume_within(clauses, workers=1, short_width=5, cand_limit=5000, del_limit=2_000_000):
    """
    Intra-set subsumption: use short clauses (len ≤ short_width) to delete strict supersets within 'clauses'.
    Returns (new_clauses, removed_count).
    """
    if not clauses:
        return clauses, 0
    # collect short clauses
    shorts = [c for c in clauses if len(c) <= short_width]
    if not shorts:
        return clauses, 0
    kept, removed = subsume_by_shorts(clauses, shorts, workers=workers,
                                      cand_limit=cand_limit, del_limit=del_limit)
    return kept, removed


# ----------------------------------------------------------------------
# DP elimination per variable (with targeted UP and subsumption)
# ----------------------------------------------------------------------

def dp_eliminate_one(clauses, v, elim_vars, *,
                     max_new=2_000_000,
                     max_width=26,
                     workers=1,
                     abort_on_explode=False,
                     up_rounds=2,
                     short_w=5,
                     cand_limit=5000,
                     del_limit=2_000_000,
                     verbose=False):
    """
    Eliminate variable v via DP with:
      - targeted UP limited to elim_vars and to POS∪NEG
      - parallel resolvent generation
      - subsumption (short resolvents vs REST; intra-RES)
    Returns (new_clauses, eliminated:bool, exploded:bool, skipped:bool)
    """
    # Split by polarity
    pos, neg, rest = [], [], []
    for c in clauses:
        s = set(c)
        if v in s:
            pos.append(c)
        elif -v in s:
            neg.append(c)
        else:
            rest.append(c)

    if verbose:
        print(f"[STAT] var {v}: |pos|={len(pos)}, |neg|={len(neg)}, |rest|={len(rest)}", file=sys.stderr)

    if not pos and not neg:
        return clauses, False, False, False

    # Targeted UP limited to elim_vars on POS∪NEG
    if up_rounds > 0:
        S = targeted_up_elim_only(pos, neg, elim_vars, max_rounds=up_rounds)
        new_pos, new_neg, moved_rest = [], [], []
        for c in S:
            if v in c:
                new_pos.append(c)
            elif -v in c:
                new_neg.append(c)
            else:
                moved_rest.append(c)
        pos, neg = new_pos, new_neg
        if moved_rest:
            rest.extend(moved_rest)

    # Pure-literal shortcut for v ONLY (existential projection is exact)
    if pos and not neg:
        # keep neg + rest, drop pos
        new_cs = dedup_clauses(rest + neg)
        if verbose:
            print(f"[OK] var {v} eliminated by PLE(+). new_clauses={len(new_cs)}", file=sys.stderr)
        return new_cs, True, False, False
    if neg and not pos:
        new_cs = dedup_clauses(rest + pos)
        if verbose:
            print(f"[OK] var {v} eliminated by PLE(-). new_clauses={len(new_cs)}", file=sys.stderr)
        return new_cs, True, False, False

    # Explosion pre-guard
    est_pairs = len(pos) * len(neg)
    if max_new >= 0 and est_pairs > max_new:
        if abort_on_explode:
            if verbose:
                print(f"[FATAL] pre-guard explode var {v}: est_pairs={est_pairs} > max-new={max_new}", file=sys.stderr)
            return clauses, False, True, False
        else:
            if verbose:
                print(f"[SKIP] var {v} skipped by pre-guard: est_pairs={est_pairs} > max-new={max_new}", file=sys.stderr)
            return clauses, False, False, True

    # Parallel resolvent generation
    RES, exploded, skipped_mid = parallel_resolvents(pos, neg, v, max_width, workers, max_new, abort_on_explode)
    if exploded:
        if verbose:
            print(f"[FATAL] mid-guard explode var {v} while generating resolvents", file=sys.stderr)
        return clauses, False, True, False
    if skipped_mid:
        if verbose:
            print(f"[SKIP] var {v} skipped mid-run due to max-new overflow", file=sys.stderr)
        return clauses, False, False, True

    # Subsumption: short resolvents kill supersets in REST
    if short_w > 0:
        res_shorts = [r for r in RES if len(r) <= short_w]
    else:
        res_shorts = []
    if res_shorts:
        rest, rm1 = subsume_by_shorts(rest, res_shorts, workers=workers,
                                      cand_limit=cand_limit, del_limit=del_limit)
        if verbose:
            print(f"[INFO] subsume REST by short RES: removed={rm1}", file=sys.stderr)

    # Optional intra-RES subsumption (short→long)
    if res_shorts:
        RES, rm2 = subsume_within(RES, workers=workers, short_width=short_w,
                                  cand_limit=cand_limit, del_limit=del_limit)
        if verbose:
            print(f"[INFO] subsume within RES: removed={rm2}", file=sys.stderr)

    new_cs = dedup_clauses(rest + RES)
    if verbose:
        print(f"[OK] var {v} eliminated. clauses -> {len(new_cs)} (from {len(clauses)})", file=sys.stderr)
    return new_cs, True, False, False


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="DP elimination on specified ∃ vars (CNF in/out), with targeted propagation and subsumption.")
    ap.add_argument("--in", dest="inp", required=True, help="input DIMACS/QDIMACS")
    ap.add_argument("--out", dest="out", required=True, help="output DIMACS")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--elim-vars", help="comma-separated var ids, e.g., 1,2,3")
    g.add_argument("--elim-file", help="file with var ids, one per line (ints)")
    ap.add_argument("--max-new", type=int, default=3_000_000, help="max new resolvents per var (guard; -1 disables)")
    ap.add_argument("--max-width", type=int, default=26, help="max resolvent width (0=unbounded; risky)")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 1) // 2), help="parallel workers")
    ap.add_argument("--abort-on-explode", action="store_true", help="abort entire run if guard exceeded")
    ap.add_argument("--up-rounds", type=int, default=2, help="targeted UP rounds (only on ELIM_VARS, only in POS∪NEG)")
    ap.add_argument("--short-w", type=int, default=5, help="short clause width for subsumption (0 disables)")
    ap.add_argument("--cand-limit", type=int, default=5000, help="per-short-clause candidate cap")
    ap.add_argument("--del-limit", type=int, default=2_000_000, help="global deletion cap in subsumption")
    ap.add_argument("--verbose", action="store_true", help="print progress/stats to stderr")
    args = ap.parse_args()

    comments, nvars, clauses = parse_dimacs(args.inp)

    # Load elimination list
    if args.elim_vars:
        elim_vars = [int(x) for x in args.elim_vars.split(",") if x.strip()]
    else:
        with open(args.elim_file, "r") as f:
            elim_vars = [int(line.strip()) for line in f if line.strip()]
    elim_vars = [v for v in elim_vars if v > 0]

    # Optional: order elim_vars by increasing |Pos|*|Neg| (cheap heuristic)
    # We compute quick stats once to avoid repeated scans
    def pos_neg_counts(v):
        pc = nc = 0
        for c in clauses:
            s = set(c)
            if v in s: pc += 1
            elif -v in s: nc += 1
        return pc, nc

    # If you prefer input order, comment out the sorting below.
    counts = []
    for v in elim_vars:
        pc, nc = pos_neg_counts(v)
        counts.append((pc*nc, pc, nc, v))
    elim_vars_sorted = [v for _,_,_,v in sorted(counts, key=lambda t: t[0])]

    start = time.time()
    eliminated_any = False

    for v in elim_vars_sorted:
        if args.verbose:
            pc, nc, *_ = [t for t in counts if t[3]==v][0]
            print(f"[BEGIN] var {v} (est_pairs={pc})", file=sys.stderr)
        clauses, eliminated, exploded, skipped = dp_eliminate_one(
            clauses, v, elim_vars=set(elim_vars),
            max_new=args.max_new,
            max_width=args.max_width,
            workers=args.workers,
            abort_on_explode=args.abort_on_explode,
            up_rounds=args.up_rounds,
            short_w=args.short_w,
            cand_limit=args.cand_limit,
            del_limit=args.del_limit,
            verbose=args.verbose
        )
        if exploded:
            print(f"[FATAL] Explosion guard hit on var {v}. Aborting.", file=sys.stderr)
            sys.exit(2)
        if eliminated:
            eliminated_any = True
        elif skipped and args.verbose:
            print(f"[NOTE] var {v} not eliminated (skipped by guard).", file=sys.stderr)

    write_dimacs(args.out, comments, nvars, clauses)

    if args.verbose:
        dt = time.time() - start
        print(f"[DONE] wrote {len(clauses)} clauses -> {args.out} in {dt:.2f}s", file=sys.stderr)


if __name__ == "__main__":
    mp.freeze_support()
    main()
