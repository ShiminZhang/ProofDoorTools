import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the scripts directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.absorption_analysis import (
    check_clause_absorption,
    compute_wire,
    compute_wire_for_formula,
    construct_clause
)
from scripts.utils.process_cnf import CNF

class TestAbsorptionAnalysis(unittest.TestCase):
    def setUp(self):
        # Create a mock CNF object for testing
        self.mock_cnf = MagicMock(spec=CNF)
        self.mock_cnf.literal_set = {1, 2, 3, 4, 5}
        self.mock_cnf.append_clause.return_value = "mock_formula"

    @patch('absorption_analysis.subprocess.run')
    def test_check_clause_absorption_success(self, mock_run):
        # Mock subprocess.run to return a successful result
        mock_result = MagicMock()
        mock_result.stdout = "PDLOG 1"
        mock_run.return_value = mock_result

        clause = [1, 2, 3]
        result = check_clause_absorption(clause, self.mock_cnf)
        self.assertTrue(result)
        self.assertEqual(mock_run.call_count, 3)  # Called once for each literal

    @patch('absorption_analysis.subprocess.run')
    def test_check_clause_absorption_failure(self, mock_run):
        # Mock subprocess.run to return a result that indicates failure
        mock_result = MagicMock()
        mock_result.stdout = "PDLOG 2"  # Different from the literal being checked
        mock_run.return_value = mock_result

        clause = [1, 2, 3]
        result = check_clause_absorption(clause, self.mock_cnf)
        self.assertFalse(result)

    def test_compute_wire(self):
        # Create two CNF objects with overlapping literals
        cnf_a = MagicMock(spec=CNF)
        cnf_a.literal_set = {1, 2, 3, 4}
        cnf_b = MagicMock(spec=CNF)
        cnf_b.literal_set = {3, 4, 5, 6}

        result = compute_wire(cnf_a, cnf_b)
        expected = {3, 4}
        self.assertEqual(result, expected)

    def test_compute_wire_for_formula(self):
        # Create a mock CNF object with get_A and get_B methods
        mock_cnf = MagicMock(spec=CNF)
        mock_cnf.get_A.return_value = MagicMock(spec=CNF)
        mock_cnf.get_B.return_value = MagicMock(spec=CNF)
        mock_cnf.get_A.return_value.literal_set = {1, 2, 3}
        mock_cnf.get_B.return_value.literal_set = {3, 4, 5}

        result = compute_wire_for_formula(mock_cnf, 1)
        expected = {3}
        self.assertEqual(result, expected)

    def test_construct_clause(self):
        # Test with a simple set of literals
        literals = [1, 2, 3]
        result = construct_clause(literals)
        
        # Should generate 2^n - 1 clauses (where n is number of literals)
        self.assertEqual(len(result), 7)  # 2^3 - 1 = 7
        
        # Check that all clauses contain valid literals
        for clause in result:
            self.assertTrue(all(lit in literals for lit in clause))
        
        # Check specific clauses
        self.assertIn([1], result)
        self.assertIn([2], result)
        self.assertIn([3], result)
        self.assertIn([1, 2], result)
        self.assertIn([1, 3], result)
        self.assertIn([2, 3], result)
        self.assertIn([1, 2, 3], result)

    def test_construct_clause_empty(self):
        # Test with empty input
        result = construct_clause([])
        self.assertEqual(result, [])

    def test_construct_clause_single(self):
        # Test with single literal  
        result = construct_clause([1])
        self.assertEqual(result, [[1]])

if __name__ == '__main__':
    unittest.main() 