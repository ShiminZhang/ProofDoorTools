import math
import os

def ceil_log2(x):
    if x <= 1:
        return 1
    return math.ceil(math.log2(x))

def _parse_smtcnf_literal_var(token):
    """From a token 'v123' or 'Not(v123)' return variable index (e.g. 123), or None."""
    token = (token or "").strip()
    if not token:
        return None
    if token.startswith("Not(v") and ")" in token:
        try:
            return int(token[5 : token.index(")")])
        except ValueError:
            return None
    if token.startswith("v"):
        try:
            return int(token[1:])
        except ValueError:
            return None
    return None


def _smtcnf_is_dimacs(filepath):
    """Peek at file: if it has 'p cnf' header, treat as DIMACS (e.g. pddef 3 .smtcnf)."""
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return False
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("c"):
                    continue
                if line.startswith("p ") and " cnf " in line:
                    return True
                return False
    except Exception:
        return False
    return False  # no non-comment line


def theoretical_bits_smtcnf(filepath):
    """
    Theoretical bit size for an smtcnf file.
    - If file has 'p cnf' header (DIMACS, e.g. pddef 3): use same formula as theoretical_bits_dimacs.
    - Else one clause per line, literals like v123 or Not(v123).
    """
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        return 0
    if _smtcnf_is_dimacs(filepath):
        return theoretical_bits_dimacs(filepath)
    n = 0
    clause_sizes = []
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("c") or line.startswith("p"):
                continue
            tokens = line.split()
            literals = [t for t in tokens if _parse_smtcnf_literal_var(t) is not None]
            if not literals:
                continue
            for t in literals:
                v = _parse_smtcnf_literal_var(t)
                if v is not None and v > n:
                    n = v
            clause_sizes.append(len(literals))
    if not clause_sizes:
        return 0
    m = len(clause_sizes)
    L = sum(clause_sizes)
    log_n = ceil_log2(n)
    log_m = ceil_log2(m)
    log_L = ceil_log2(L)
    total_bits = log_n + log_m
    for k in clause_sizes:
        total_bits += log_L
        total_bits += k * (log_n + 1)
    return total_bits

def theoretical_bits_dimacs(filepath):
    # assume the file is a DIMACS CNF file
    n = 0
    m = 0
    clause_sizes = []

    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("c"):
                continue
            if line.startswith("p"):
                parts = line.split()
                n = int(parts[2])
                m = int(parts[3])
            else:
                literals = line.split()
                # remove trailing 0
                literals = literals[:-1]
                clause_sizes.append(len(literals))

    L = sum(clause_sizes)

    log_n = ceil_log2(n)
    log_m = ceil_log2(m)
    log_L = ceil_log2(L)

    total_bits = log_n + log_m

    for k in clause_sizes:
        total_bits += log_L
        total_bits += k * (log_n + 1)

    return total_bits

def get_bits_from_cnf(filepath):
    return theoretical_bits_dimacs(filepath)