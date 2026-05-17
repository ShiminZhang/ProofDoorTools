#!/usr/bin/env python3
"""
Unit tests for reverse_spd_to_mpd.py and the --show_success --reverse
extension in manage_spd_computation.py.

Run from the repo root:
    python scripts/strongest_pd/test_reverse_spd_to_mpd.py
"""

import csv
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import z3

from strongest_pd.reverse_spd_to_mpd import _clauses_to_z3, negate_and_to_cnf, process_entry
from strongest_pd.manage_spd_computation import get_reverse_successes
from utils.paths import get_spd7_success_csv, get_reverse_spd_cnf_dir


# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------

def _cnf_tokens_to_z3(cnf_tokens):
    """Convert negate_and_to_cnf token output back to a Z3 formula."""
    if not cnf_tokens:
        return z3.BoolVal(True)
    z3_clauses = []
    for clause in cnf_tokens:
        if not clause:
            # empty clause = False
            return z3.BoolVal(False)
        lits = []
        for tok in clause:
            if tok.startswith("Not(") and tok.endswith(")"):
                v = int(tok[4:-1].lstrip("v"))
                lits.append(z3.Not(z3.Bool(f"v{v}")))
            else:
                v = int(tok.lstrip("v"))
                lits.append(z3.Bool(f"v{v}"))
        z3_clauses.append(z3.Or(lits) if len(lits) > 1 else lits[0])
    return z3.And(z3_clauses) if len(z3_clauses) > 1 else z3_clauses[0]


def _is_valid(expr):
    """Return True iff expr is a tautology (valid in all models)."""
    s = z3.Solver()
    s.add(z3.Not(expr))
    return s.check() == z3.unsat


def _negation_is_correct(clauses):
    """
    Semantic correctness check: verifies that negate_and_to_cnf(clauses)
    produces a formula logically equivalent to ¬(original formula).
    """
    original, _ = _clauses_to_z3(clauses)
    cnf_tokens = negate_and_to_cnf(clauses)
    negated = _cnf_tokens_to_z3(cnf_tokens)
    # original ↔ ¬negated  ≡  (original → ¬negated) ∧ (¬negated → original)
    return _is_valid(original == z3.Not(negated))


# ---------------------------------------------------------------------------
# Tests for _clauses_to_z3
# ---------------------------------------------------------------------------

class TestClausesToZ3(unittest.TestCase):

    def test_empty_clauses_is_true(self):
        formula, var_map = _clauses_to_z3([])
        self.assertTrue(z3.is_true(formula))
        self.assertEqual(var_map, {})

    def test_empty_clause_inside_is_false(self):
        formula, var_map = _clauses_to_z3([[]])
        self.assertTrue(z3.is_false(formula))
        self.assertEqual(var_map, {})

    def test_single_unit_positive(self):
        formula, var_map = _clauses_to_z3([[1]])
        self.assertIn(1, var_map)
        s = z3.Solver()
        # formula should be satisfiable only when v1=True
        s.add(formula)
        s.add(z3.Not(var_map[1]))
        self.assertEqual(s.check(), z3.unsat)

    def test_single_unit_negative(self):
        formula, var_map = _clauses_to_z3([[-1]])
        self.assertIn(1, var_map)
        s = z3.Solver()
        s.add(formula)
        s.add(var_map[1])
        self.assertEqual(s.check(), z3.unsat)

    def test_two_unit_clauses(self):
        # (v1) ∧ (v2)
        formula, var_map = _clauses_to_z3([[1], [2]])
        s = z3.Solver()
        s.add(formula)
        s.add(z3.Not(var_map[1]))
        self.assertEqual(s.check(), z3.unsat)  # v1 must be True

    def test_disjunctive_clause(self):
        # (v1 ∨ v2): satisfiable, but v1=False,v2=False is UNSAT under formula
        formula, var_map = _clauses_to_z3([[1, 2]])
        s = z3.Solver()
        s.add(formula)
        s.add(z3.Not(var_map[1]))
        s.add(z3.Not(var_map[2]))
        self.assertEqual(s.check(), z3.unsat)


# ---------------------------------------------------------------------------
# Tests for negate_and_to_cnf — boundary cases
# ---------------------------------------------------------------------------

class TestNegateAndToCnfBoundary(unittest.TestCase):

    def test_empty_clauses_negates_to_false(self):
        # ¬True = False: one empty clause
        result = negate_and_to_cnf([])
        self.assertEqual(result, [[]])

    def test_false_clauses_negates_to_true(self):
        # ¬False = True: no clauses
        result = negate_and_to_cnf([[]])
        self.assertEqual(result, [])

    def test_unit_clause_positive(self):
        # ¬(v1) = {¬v1}
        result = negate_and_to_cnf([[1]])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 1)
        self.assertIn("Not(v1)", result[0])

    def test_unit_clause_negative(self):
        # ¬(¬v1) = {v1}
        result = negate_and_to_cnf([[-1]])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 1)
        self.assertIn("v1", result[0])


# ---------------------------------------------------------------------------
# Tests for negate_and_to_cnf — semantic correctness
# ---------------------------------------------------------------------------

class TestNegateAndToCnfSemantic(unittest.TestCase):
    """
    For each test case, verify that the output CNF is logically equivalent
    to the negation of the input formula using Z3.
    """

    def _check(self, clauses):
        self.assertTrue(
            _negation_is_correct(clauses),
            msg=f"Negation incorrect for clauses: {clauses}",
        )

    def test_conjunction_of_units(self):
        # ¬(v1 ∧ v2) = ¬v1 ∨ ¬v2  (single clause)
        clauses = [[1], [2]]
        self._check(clauses)
        result = negate_and_to_cnf(clauses)
        # Result must be a single clause containing both negated literals
        self.assertEqual(len(result), 1)
        self.assertIn("Not(v1)", result[0])
        self.assertIn("Not(v2)", result[0])

    def test_single_disjunction(self):
        # ¬(v1 ∨ v2) = ¬v1 ∧ ¬v2  (two unit clauses)
        clauses = [[1, 2]]
        self._check(clauses)
        result = negate_and_to_cnf(clauses)
        all_lits = {tok for clause in result for tok in clause}
        self.assertIn("Not(v1)", all_lits)
        self.assertIn("Not(v2)", all_lits)

    def test_three_variable_cnf(self):
        # (v1 ∨ v2) ∧ (¬v2 ∨ v3)
        self._check([[1, 2], [-2, 3]])

    def test_larger_cnf(self):
        # Typical clause structure with 4 variables
        self._check([[1, 2, 3], [-1, 4], [-3, -4], [2, -4]])

    def test_unsatisfiable_input(self):
        # v1 ∧ ¬v1 = False  →  negation = True  →  no clauses
        self._check([[1], [-1]])
        result = negate_and_to_cnf([[1], [-1]])
        self.assertEqual(result, [])

    def test_tautological_single_clause(self):
        # (v1 ∨ ¬v1) = True  →  negation = False  →  one empty clause
        # Note: tautological clauses are dropped by _dedupe_clauses/expand_to_cnf,
        # so the formula reduces to True before negation.
        self._check([[1, -1]])

    def test_double_negation_roundtrip(self):
        # negate(negate(F)) should be equivalent to F.
        clauses = [[1, 2], [-2, 3], [-1, -3]]
        first_neg_tokens = negate_and_to_cnf(clauses)
        # Convert token output back to int clauses for second negation.
        int_clauses = []
        for clause in first_neg_tokens:
            int_clause = []
            for tok in clause:
                if tok.startswith("Not("):
                    int_clause.append(-int(tok[4:-1].lstrip("v")))
                else:
                    int_clause.append(int(tok.lstrip("v")))
            int_clauses.append(int_clause)
        second_neg_tokens = negate_and_to_cnf(int_clauses)

        original, _ = _clauses_to_z3(clauses)
        roundtrip = _cnf_tokens_to_z3(second_neg_tokens)
        self.assertTrue(_is_valid(original == roundtrip))


# ---------------------------------------------------------------------------
# Tests for get_reverse_successes
# ---------------------------------------------------------------------------

class TestGetReverseSuccesses(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.K = 6
        self.log_dir = os.path.join(self.tmpdir, f"k_{self.K}")
        os.makedirs(self.log_dir)

    def _write_log(self, name, i, job_id, content):
        path = os.path.join(self.log_dir, f"{name}.{self.K}.{job_id}_{i}.log")
        with open(path, "w") as f:
            f.write(content)

    def _run(self, instances=None):
        with patch(
            "strongest_pd.manage_spd_computation.SLURM_LOG_DIR_REV", self.tmpdir
        ):
            return get_reverse_successes(self.K, instances)

    def test_single_success(self):
        name = "inst_a"
        i = 3
        self._write_log(name, i, "99001", f"Interpolant validity check passed for {name}.{self.K}.{i}\n")
        result = self._run()
        self.assertIn((name, self.K, i), result)

    def test_single_failure(self):
        name = "inst_b"
        i = 2
        self._write_log(name, i, "99002", "ERROR: interpolant validity check FAILED\n")
        result = self._run()
        self.assertNotIn((name, self.K, i), result)

    def test_partial_success(self):
        name = "inst_c"
        for i in range(self.K):
            content = (
                f"Interpolant validity check passed for {name}.{self.K}.{i}\n"
                if i % 2 == 0
                else "FAILED\n"
            )
            self._write_log(name, i, 99010 + i, content)
        result = self._run()
        passed_indices = {idx for (n, _, idx) in result if n == name}
        self.assertEqual(passed_indices, {0, 2, 4})

    def test_instances_filter(self):
        for name in ("alpha", "beta"):
            self._write_log(
                name, 0, 99020,
                f"Interpolant validity check passed for {name}.{self.K}.0\n"
            )
        result = self._run(instances=["alpha"])
        names_in_result = {n for (n, _, _) in result}
        self.assertIn("alpha", names_in_result)
        self.assertNotIn("beta", names_in_result)

    def test_multiple_logs_same_index_latest_wins(self):
        # Two logs for (name, i=1); only the latest (sorted last) has success.
        name = "inst_d"
        i = 1
        self._write_log(name, i, "10000", "FAILED\n")
        self._write_log(name, i, "10001", f"Interpolant validity check passed for {name}.{self.K}.{i}\n")
        result = self._run()
        self.assertIn((name, self.K, i), result)

    def test_empty_log_dir(self):
        result = self._run()
        self.assertEqual(result, [])

    def test_missing_log_dir(self):
        with patch(
            "strongest_pd.manage_spd_computation.SLURM_LOG_DIR_REV",
            os.path.join(self.tmpdir, "nonexistent"),
        ):
            result = get_reverse_successes(self.K)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Integration test for process_entry
# ---------------------------------------------------------------------------

class TestProcessEntry(unittest.TestCase):
    """
    Write a small QDIMACS file, call process_entry, and verify the output CNF
    is the negation of the input formula.
    """

    def _make_qdimacs(self, clauses, path):
        all_vars = sorted({abs(l) for clause in clauses for l in clause})
        max_var = max(all_vars) if all_vars else 0
        with open(path, "w") as f:
            f.write(f"p cnf {max_var} {len(clauses)}\n")
            if all_vars:
                f.write("e " + " ".join(str(v) for v in all_vars) + " 0\n")
            for clause in clauses:
                f.write(" ".join(str(l) for l in clause) + " 0\n")

    def _read_dimacs(self, path):
        clauses = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("p"):
                    continue
                lits = [int(x) for x in line.split() if x != "0"]
                clauses.append(lits)
        return clauses

    def test_process_entry_simple(self):
        input_clauses = [[1, 2], [-1, 3]]
        with tempfile.TemporaryDirectory() as tmpdir:
            interp_dir = os.path.join(tmpdir, "interpolants_def7", "4")
            out_dir = os.path.join(tmpdir, "cnfs_spd7", "4")
            os.makedirs(interp_dir)
            os.makedirs(out_dir)

            interp_path = os.path.join(interp_dir, "test_inst.4.0.interpolant")
            out_path = os.path.join(out_dir, "test_inst.4.0.cnf")
            self._make_qdimacs(input_clauses, interp_path)

            with (
                patch("strongest_pd.reverse_spd_to_mpd.get_interpolant_dir", return_value=interp_dir),
                patch("strongest_pd.reverse_spd_to_mpd.get_reverse_spd_cnf_dir", return_value=out_dir),
            ):
                process_entry("test_inst", 4, 0, verify=False)

            self.assertTrue(os.path.exists(out_path))
            self.assertGreater(os.path.getsize(out_path), 0)

            # Semantic check: output CNF ≡ ¬(input formula)
            output_clauses = self._read_dimacs(out_path)
            original, _ = _clauses_to_z3(input_clauses)
            output_formula = _clauses_to_z3(output_clauses)[0]
            self.assertTrue(_is_valid(output_formula == z3.Not(original)))

    def test_process_entry_skip_existing(self):
        # If output already exists and is non-empty, process_entry should skip.
        with tempfile.TemporaryDirectory() as tmpdir:
            interp_dir = os.path.join(tmpdir, "interpolants_def7", "4")
            out_dir = os.path.join(tmpdir, "cnfs_spd7", "4")
            os.makedirs(interp_dir)
            os.makedirs(out_dir)

            interp_path = os.path.join(interp_dir, "test_inst.4.0.interpolant")
            out_path = os.path.join(out_dir, "test_inst.4.0.cnf")
            self._make_qdimacs([[1]], interp_path)

            sentinel = "p cnf 0 0\n"
            with open(out_path, "w") as f:
                f.write(sentinel)

            with (
                patch("strongest_pd.reverse_spd_to_mpd.get_interpolant_dir", return_value=interp_dir),
                patch("strongest_pd.reverse_spd_to_mpd.get_reverse_spd_cnf_dir", return_value=out_dir),
            ):
                process_entry("test_inst", 4, 0, force_refresh=False, verify=False)

            with open(out_path) as f:
                self.assertEqual(f.read(), sentinel)  # untouched

    def test_process_entry_force_refresh(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            interp_dir = os.path.join(tmpdir, "interpolants_def7", "4")
            out_dir = os.path.join(tmpdir, "cnfs_spd7", "4")
            os.makedirs(interp_dir)
            os.makedirs(out_dir)

            interp_path = os.path.join(interp_dir, "test_inst.4.0.interpolant")
            out_path = os.path.join(out_dir, "test_inst.4.0.cnf")
            self._make_qdimacs([[1]], interp_path)

            sentinel = "p cnf 0 0\n"
            with open(out_path, "w") as f:
                f.write(sentinel)

            with (
                patch("strongest_pd.reverse_spd_to_mpd.get_interpolant_dir", return_value=interp_dir),
                patch("strongest_pd.reverse_spd_to_mpd.get_reverse_spd_cnf_dir", return_value=out_dir),
            ):
                process_entry("test_inst", 4, 0, force_refresh=True, verify=False)

            with open(out_path) as f:
                content = f.read()
            self.assertNotEqual(content, sentinel)


# ---------------------------------------------------------------------------
# Tests for path helpers
# ---------------------------------------------------------------------------

class TestPaths(unittest.TestCase):

    def test_spd7_success_csv_contains_k(self):
        path = get_spd7_success_csv(10)
        self.assertIn("10", path)
        self.assertTrue(path.endswith(".csv"))

    def test_reverse_spd_cnf_dir_contains_k(self):
        d = get_reverse_spd_cnf_dir(10)
        self.assertIn("10", d)
        self.assertIn("spd7", d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
