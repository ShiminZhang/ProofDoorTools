import argparse
import random
from typing import List
from utils.process_cnf import CNF
# from process_cnf import CNF
PERMUTE_LIMIT = 20
class ScrambleType:
    CLAUSE = "clause"
    ITERATION = "iteration"
    CLAUSE_AND_ITERATION = "clause_and_iteration"

SCRAMBLE_TYPES = [
    ScrambleType.CLAUSE,
    ScrambleType.ITERATION,
    ScrambleType.CLAUSE_AND_ITERATION,
]

def _build_iter_blocks(cnf: CNF) -> List[List[List[int]]]:
    clauses = cnf.get_clauses()
    iter_map = cnf.get_iter_map()
    if not iter_map:
        return [clauses]
    iter_keys = sorted(iter_map.keys())
    blocks = []
    for idx, iter_idx in enumerate(iter_keys):
        start = iter_map[iter_idx]
        end = len(clauses) if idx + 1 == len(iter_keys) else iter_map[iter_keys[idx + 1]]
        blocks.append(clauses[start:end])
    return blocks


def _cnf_from_blocks(blocks: List[List[List[int]]]) -> CNF:
    new_clauses: List[List[int]] = [clause for block in blocks for clause in block]
    new_cnf = CNF()
    new_cnf.init_with_clauses(new_clauses)
    new_iter_map = {}
    clause_index = 0
    for iter_index, block in enumerate(blocks):
        new_iter_map[iter_index] = clause_index
        clause_index += len(block)
    new_cnf.iter_map = new_iter_map
    new_cnf.K = max(0, len(blocks) - 1)
    return new_cnf


def scramble_cnf_clauses(cnf: CNF) -> CNF:
    # shuffle all clauses, iteration boundaries are broken
    clauses = cnf.get_clauses()[:]
    random.shuffle(clauses)
    new_cnf = CNF()
    new_cnf.init_with_clauses(clauses)
    new_cnf.iter_map = cnf.iter_map
    new_cnf.K = cnf.K
    return new_cnf

def scramble_cnf_iterations(cnf: CNF) -> CNF:
    # shuffle iteration blocks, keep clause order within each iteration
    blocks = _build_iter_blocks(cnf)
    random.shuffle(blocks)
    return _cnf_from_blocks(blocks)


def scramble_cnf_clause_and_iteration(cnf: CNF) -> CNF:
    # shuffle iteration blocks, then shuffle clauses inside each block
    blocks = _build_iter_blocks(cnf)
    random.shuffle(blocks)
    for block in blocks:
        random.shuffle(block)
    return _cnf_from_blocks(blocks)

def scramble_cnf(cnf_path: str, output_path: str, permute_type: ScrambleType = ScrambleType.CLAUSE) -> str:
    print(f"Scrambling {cnf_path} with {permute_type} to {output_path}")
    cnf = CNF.from_file(cnf_path)
    if permute_type == ScrambleType.CLAUSE:
        cnf = scramble_cnf_clauses(cnf)
    elif permute_type == ScrambleType.ITERATION:
        cnf = scramble_cnf_iterations(cnf)
    elif permute_type == ScrambleType.CLAUSE_AND_ITERATION:
        cnf = scramble_cnf_clause_and_iteration(cnf)
    else:
        raise ValueError(f"Invalid scramble type: {permute_type}")

    cnf.to_dimacs(output_path)
    return output_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scramble CNF clauses or iterations.")
    parser.add_argument("--cnf-path", required=True, help="Path to input CNF file.")
    parser.add_argument("--output-path", required=True, help="Path to output CNF file.")
    parser.add_argument(
        "--permute-type",
        default=ScrambleType.CLAUSE,
        choices=SCRAMBLE_TYPES,
        help="Permutation type to apply.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    scramble_cnf(
        cnf_path=args.cnf_path,
        output_path=args.output_path,
        permute_type=args.permute_type,
    )


if __name__ == "__main__":
    main()

    