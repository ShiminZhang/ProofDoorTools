from process_cnf import CNF
from paths import get_wires_dir
from utils.absorption_analysis import compute_wire_and_save
import os
import json
import argparse


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cnf_path", type=str, required=True)
    args = parser.parse_args()
    cnf_path = args.cnf_path
    compute_wire_and_save(CNF.from_file(cnf_path))

if __name__ == "__main__":
    main()
