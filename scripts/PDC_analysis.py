# check:
# 1. correation between PDC time and N of variables
# 2. correation between PDC time and interpolant size
# 3. correation between PDC time and instance solving time
# from process_interpolants import GetData
from utils.utils import GetData
import pandas as pd
import argparse
import os

def get_PDC_time(K,UseCache):
    saved="benchmark_times.csv"
    if os.path.exists(saved):
        df = pd.read_csv(saved)
        return df
    else:
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--formula_category", type=str, default="QF_FD")
    parser.add_argument("--K", type=str, default="K1")
    parser.add_argument("--solver", type=str, default="cadical")
    parser.add_argument("--UseCache", type=bool, default=True)
    args = parser.parse_args()

    cadical_data,cadical_map,cadical_par2,cadical_mem = GetData(f"./ProofDoorBenchmark/{args.formula_category}/{args.K}/", args.solver, args.UseCache)
