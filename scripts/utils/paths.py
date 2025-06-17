import os

def get_interpolant_dir(k_value):
    return f"./ProofDoorBenchmark/interpolants/{k_value}/"

def get_branching_order_log_dir():
    if not os.path.exists(f"./ProofDoorBenchmark/branching_order_logs/"):
        os.makedirs(f"./ProofDoorBenchmark/branching_order_logs/")
    return f"./ProofDoorBenchmark/branching_order_logs/"

def get_branching_order_dir(k_value):
    if not os.path.exists(f"./ProofDoorBenchmark/branching_orders/{k_value}/"):
        os.makedirs(f"./ProofDoorBenchmark/branching_orders/{k_value}/")
    return f"./ProofDoorBenchmark/branching_orders/{k_value}/"

def get_PDS_data_dir():
    return f"./ProofSizeMap/data/"

def get_CNF_dir(k_value):
    return f"./ProofDoorBenchmark/cnfs/{k_value}/"

def get_interpolant_cnf_dir():
    return f"./ProofDoorBenchmark/interpolant_as_cnfs/"

def get_interpolant_dimacs_dir():
    return f"./ProofDoorBenchmark/combined_cnfs/"

def get_PDS_dir(k_value):
    if not os.path.exists(f"./ProofSizeMap/data/{k_value}/"):
        os.makedirs(f"./ProofSizeMap/data/{k_value}/")
    return f"./ProofSizeMap/data/{k_value}/"

def get_smts_dir(k_value):
    return f"./ProofDoorBenchmark/smts/{k_value}/"

def get_cnfs_dir(k_value):
    return f"./ProofDoorBenchmark/cnfs/{k_value}/"

def get_exp_pbh_dir(k_value):
    if not os.path.exists(f"./ProofDoorBenchmark/exp_pbh/"):
        os.makedirs(f"./ProofDoorBenchmark/exp_pbh/")
    if not os.path.exists(f"./ProofDoorBenchmark/exp_pbh/{k_value}/"):
        os.makedirs(f"./ProofDoorBenchmark/exp_pbh/{k_value}/")
    return f"./ProofDoorBenchmark/exp_pbh/{k_value}/"

def get_wires_dir(k_value):
    if not os.path.exists("./ProofDoorBenchmark/wires/"):
        os.makedirs("./ProofDoorBenchmark/wires/")
    if not os.path.exists(f"./ProofDoorBenchmark/wires/{k_value}/"):
        os.makedirs(f"./ProofDoorBenchmark/wires/{k_value}/")
    return f"./ProofDoorBenchmark/wires/{k_value}/"

def get_figures_dir():
    if not os.path.exists("./figures/"):
        os.makedirs("./figures/")
    return f"./figures/"

def get_absorption_experiments_dir():
    if not os.path.exists("./ProofDoorBenchmark/absorption_experiments/"):
        os.makedirs("./ProofDoorBenchmark/absorption_experiments/")
    return f"./ProofDoorBenchmark/absorption_experiments/"