import os

def get_aiger_dir():
    if not os.path.exists(f"./ProofDoorBenchmark/aigs/"):
        os.makedirs(f"./ProofDoorBenchmark/aigs/")
    return f"./ProofDoorBenchmark/aigs/"

def get_circuit_features_dir():
    return f"./ProofDoorBenchmark/aigs/features.csv"

def get_benchmark_dir():
    if not os.path.exists(f"./ProofDoorBenchmark/benchmarks/"):
        os.makedirs(f"./ProofDoorBenchmark/benchmarks/")
    return f"./ProofDoorBenchmark/benchmarks/"

def get_shuffled_cnf_dir(k_value):
    if not os.path.exists(f"./ProofDoorBenchmark/shuffled_cnfs/{k_value}/"):
        os.makedirs(f"./ProofDoorBenchmark/shuffled_cnfs/{k_value}/")
    return f"./ProofDoorBenchmark/shuffled_cnfs/{k_value}/"

def get_interpolant_dir(k_value,pddef=0):
    if pddef == 0:
        if not os.path.exists(f"./ProofDoorBenchmark/interpolants/{k_value}/"):
            os.makedirs(f"./ProofDoorBenchmark/interpolants/{k_value}/")
        return f"./ProofDoorBenchmark/interpolants/{k_value}/"
    elif pddef == 1:
        if not os.path.exists(f"./ProofDoorBenchmark/interpolants_def1/{k_value}/"):
            os.makedirs(f"./ProofDoorBenchmark/interpolants_def1/{k_value}/")
        return f"./ProofDoorBenchmark/interpolants_def1/{k_value}/"
    elif pddef == 2:
        if not os.path.exists(f"./ProofDoorBenchmark/interpolants_def2/{k_value}/"):
            os.makedirs(f"./ProofDoorBenchmark/interpolants_def2/{k_value}/")
        return f"./ProofDoorBenchmark/interpolants_def2/{k_value}/"
    else:
        if not os.path.exists(f"./ProofDoorBenchmark/interpolants_def{pddef}/{k_value}/"):
            os.makedirs(f"./ProofDoorBenchmark/interpolants_def{pddef}/{k_value}/")
        return f"./ProofDoorBenchmark/interpolants_def{pddef}/{k_value}/"

# def get_interpolant_cnf_dir_def1(k_value):
#     if not os.path.exists(f"./ProofDoorBenchmark/interpolant_as_cnfs_def1/{k_value}/"):
#         os.makedirs(f"./ProofDoorBenchmark/interpolant_as_cnfs_def1/{k_value}/")
#     return f"./ProofDoorBenchmark/interpolant_as_cnfs_def1/{k_value}/"

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

def get_sanity_dir(k_value,pddef=0):
    if not os.path.exists(f"./ProofDoorBenchmark/sanity_checks/pddef_{pddef}/{k_value}/"):
        os.makedirs(f"./ProofDoorBenchmark/sanity_checks/pddef_{pddef}/{k_value}/")
    return f"./ProofDoorBenchmark/sanity_checks/pddef_{pddef}/{k_value}/"

def get_CNF_dir(k_value):
    if not os.path.exists(f"./ProofDoorBenchmark/cnfs/{k_value}/"):
        os.makedirs(f"./ProofDoorBenchmark/cnfs/{k_value}/", exist_ok=True)
    return f"./ProofDoorBenchmark/cnfs/{k_value}/"
    
def get_DRAT(name, k_value):
    if not os.path.exists(f"./ProofDoorBenchmark/cnfs/{k_value}/{name}.{k_value}.cadicalplain.drat"):
        os.makedirs(f"./ProofDoorBenchmark/cnfs/{k_value}/", exist_ok=True)
    return f"./ProofDoorBenchmark/cnfs/{k_value}/{name}.{k_value}.cadicalplain.drat"

def get_CNF_info(name):
    if not os.path.exists(f"./ProofDoorBenchmark/cnfs/info/{name}.info.json"):
        os.makedirs(f"./ProofDoorBenchmark/cnfs/info/", exist_ok=True)
    return f"./ProofDoorBenchmark/cnfs/info/{name}.info.json"

def get_scrambled_CNF(name,k_value,permute_type,permute_index):
    file_path = f"./ProofDoorBenchmark/scrambled_cnfs/{k_value}/{permute_index}/{name}.{k_value}.{permute_type}.cnf"
    if not os.path.exists(file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    return file_path

def get_scranfilized_CNF(name,k_value,profile,seed):
    file_path = f"./ProofDoorBenchmark/scranfilized_cnfs/{profile}/seed_{seed}/{k_value}/{name}.{k_value}.scr_{profile}_s{seed}.cnf"
    if not os.path.exists(file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    return file_path

def get_scranfilized_meta(name,k_value,profile,seed):
    file_path = f"./ProofDoorBenchmark/scranfilized_cnfs/{profile}/seed_{seed}/{k_value}/{name}.{k_value}.scr_{profile}_s{seed}.meta.json"
    if not os.path.exists(file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    return file_path

def get_interpolant_cnf_dir(k_value=10, pddef=0):
    if pddef == 7:
        d = f"./ProofDoorBenchmark/interpolant_as_cnfs_spd7/{k_value}/"
        os.makedirs(d, exist_ok=True)
        return d
    if os.path.exists(f"./ProofDoorBenchmark/interpolant_as_cnfs_{pddef}/{k_value}/"):
        return f"./ProofDoorBenchmark/interpolant_as_cnfs_{pddef}/{k_value}/"
    else:
        os.makedirs(f"./ProofDoorBenchmark/interpolant_as_cnfs_{pddef}/{k_value}/")
        return f"./ProofDoorBenchmark/interpolant_as_cnfs_{pddef}/{k_value}/"

def get_interpolant_dimacs_dir(K=-1,pddef=0):
    if K == -1:
        return f"./ProofDoorBenchmark/combined_cnfs/"
    else:
        if pddef == 0:
            os.makedirs(f"./ProofDoorBenchmark/combined_cnfs/{K}/", exist_ok=True)
            return f"./ProofDoorBenchmark/combined_cnfs/{K}/"
        else:
            os.makedirs(f"./ProofDoorBenchmark/combined_cnfs/pddef_{pddef}/{K}/", exist_ok=True)
            return f"./ProofDoorBenchmark/combined_cnfs/pddef_{pddef}/{K}/"

def get_PDS_dir(k_value,pddef=0):
    if not os.path.exists(f"./ProofSizeMap/data/pddef_{pddef}/{k_value}/"):
        os.makedirs(f"./ProofSizeMap/data/pddef_{pddef}/{k_value}/")
    return f"./ProofSizeMap/data/pddef_{pddef}/{k_value}/"

def get_smts_dir(k_value,pddef=0):
    if pddef == 0:
        if not os.path.exists(f"./ProofDoorBenchmark/smts/{k_value}/"):
            os.makedirs(f"./ProofDoorBenchmark/smts/{k_value}/")
        return f"./ProofDoorBenchmark/smts/{k_value}/"
    elif pddef == 1:
        if not os.path.exists(f"./ProofDoorBenchmark/smts_def1/{k_value}/"):
            os.makedirs(f"./ProofDoorBenchmark/smts_def1/{k_value}/")
        return f"./ProofDoorBenchmark/smts_def1/{k_value}/"
    elif pddef == 2:
        if not os.path.exists(f"./ProofDoorBenchmark/smts_def2/{k_value}/"):
            os.makedirs(f"./ProofDoorBenchmark/smts_def2/{k_value}/")
        return f"./ProofDoorBenchmark/smts_def2/{k_value}/"

def get_solving_time_dir(k_value,tag="solving_time"):
    cnfs_dir = get_cnfs_dir(k_value)
    if not os.path.exists(f"{cnfs_dir}/{tag}/"):
        os.makedirs(f"{cnfs_dir}/{tag}/")
    return f"{cnfs_dir}/{tag}/"

def get_cnfs_dir(k_value):
    if not os.path.exists(f"./ProofDoorBenchmark/cnfs/{k_value}/"):
        os.makedirs(f"./ProofDoorBenchmark/cnfs/{k_value}/")
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

def get_smt_def1_dir(k_value):
    return get_smts_dir(k_value,pddef=1)

def get_figures_dir():
    if not os.path.exists("./figures/"):
        os.makedirs("./figures/")
    return f"./figures/"

def get_absorption_experiments_dir(k_value):
    if not os.path.exists("./ProofDoorBenchmark/absorption_experiments/"):
        os.makedirs("./ProofDoorBenchmark/absorption_experiments/", exist_ok=True)
    if not os.path.exists(f"./ProofDoorBenchmark/absorption_experiments/{k_value}/"):
        os.makedirs(f"./ProofDoorBenchmark/absorption_experiments/{k_value}/", exist_ok=True)
    return f"./ProofDoorBenchmark/absorption_experiments/{k_value}/"

def get_latest_PDC_result(K):
    return f"./Dashboard/SMTTranslationToCNFExperiment_results_{K}.json"


def get_latest_absorption_result(K):
    return f"./Dashboard/AbsorptionExperiment_results_{K}.json"


def get_interpolant_dependence_result_dir(pddef=1):
    """Directory for per-instance interpolant dependence CSV results (used by --manage)."""
    d = f"./ProofDoorBenchmark/interpolant_dependence_pddef_{pddef}/"
    os.makedirs(d, exist_ok=True)
    return d

def get_progressive_qdimacs_dir(k_value, tag="shared_local"):
    d = f"./ProofDoorBenchmark/qdimacs_{tag}/{k_value}/"
    os.makedirs(d, exist_ok=True)
    return d

def get_spd7_success_csv(k_value):
    os.makedirs("./results/", exist_ok=True)
    return f"./results/spd7_success_{k_value}.csv"

def get_reverse_spd_cnf_dir(k_value):
    d = f"./ProofDoorBenchmark/interpolant_as_cnfs_spd7/{k_value}/"
    os.makedirs(d, exist_ok=True)
    return d
