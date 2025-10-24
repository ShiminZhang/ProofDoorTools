import os
import argparse
from ..utils.catagory import get_instance_list

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--pddef", type=int, default=0)
    parser.add_argument("--category", type=str, default="")
    args = parser.parse_args()
    k = args.k
    original_cnf_dir = f"./ProofDoorBenchmark/cnfs/{args.k}/"
    if args.pddef == 0:
        directory = f"./ProofDoorBenchmark/combined_cnfs/{args.k}/"
        output_dir = f"./ProofDoorBenchmark/combined_cnfs/{args.k}/"
    else:
        directory = f"./ProofDoorBenchmark/combined_cnfs/pddef_{args.pddef}/{args.k}/"
        output_dir = f"./ProofDoorBenchmark/combined_cnfs/pddef_{args.pddef}/{args.k}/"
    print(directory)
    category_keys = get_instance_list(args.category)
    for file in os.listdir(directory):
        if file.endswith(f".combined.{args.k}.cnf"):
            name = file.split(".")[0]
            print(name)
            if name not in category_keys:
                continue
            print(file)
            cadical_output_file = os.path.join(output_dir, file.replace(f".combined.{k}.cnf", ".combine_cadical.log"))
            minisat_output_file = os.path.join(output_dir, file.replace(f".combined.{k}.cnf", ".combine_minisat.log"))
            # output_file = os.path.join(output_dir, file.replace(f".combined.{args.k}.cnf", ".combine_minisat.log"))
            # if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            #     continue
            cadical_cmd = f"./solvers/cadical {os.path.join(directory, file)} --plain > {cadical_output_file}"
            minisat_cmd = f"./solvers/minisat {os.path.join(directory, file)} > {minisat_output_file}"
            cnf_file = file.replace(f".combined.{args.k}.cnf", f".cnf")
            minisat_cnf_out = f"{cnf_file}.minisat.log"
            cadical_cnf_out = f"{cnf_file}.cadical.log"
            minisat_original_cmd = f"./solvers/minisat {os.path.join(original_cnf_dir, cnf_file)} > {os.path.join(original_cnf_dir, minisat_cnf_out)}"
            cadical_original_cmd = f"./solvers/cadical {os.path.join(original_cnf_dir, cnf_file)} --plain > {os.path.join(original_cnf_dir, cadical_cnf_out)}"
            # print(cmd)
            activate_python = "source ../general/bin/activate"
            wrapped=f"{activate_python} && {cadical_cmd}; {minisat_cmd}; {cadical_original_cmd}; {minisat_original_cmd}"
            slurm_output_dir="SlurmLogs/CombinePDwithFormula"
            os.makedirs(slurm_output_dir, exist_ok=True)
            slurm_output_file = os.path.join(slurm_output_dir, file.replace(".cnf", ".out"))
            slurm_cmd = f"sbatch --output={slurm_output_file} --job-name=CombinePDwithFormula --time=03:20:00 --mem=16G --wrap='{wrapped}'"
            os.system(slurm_cmd)
    pass

if __name__ == "__main__":
    main()