import os

def main():
    k = 10
    directory = f"./ProofDoorBenchmark/combined_cnfs/{k}/"
    output_dir = f"./ProofDoorBenchmark/combined_cnfs/{k}/"
    for file in os.listdir(directory):
        if file.endswith(f".combined.{k}.cnf"):
            print(file)
            # output_file = os.path.join(output_dir, file.replace(f".combined.{k}.cnf", ".combine_cadical.log"))
            output_file = os.path.join(output_dir, file.replace(f".combined.{k}.cnf", ".combine_minisat.log"))
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                continue
            # cmd = f"./solvers/cadical {os.path.join(directory, file)} --plain > {output_file}"
            cmd = f"./solvers/minisat {os.path.join(directory, file)} > {output_file}"
            # print(cmd)
            activate_python = "source ../general/bin/activate"
            wrapped=f"{activate_python} && {cmd}"
            slurm_output_dir="SlurmLogs/CombinePDwithFormula"
            os.makedirs(slurm_output_dir, exist_ok=True)
            slurm_output_file = os.path.join(slurm_output_dir, file.replace(".cnf", ".out"))
            slurm_cmd = f"sbatch --output={slurm_output_file} --job-name=CombinePDwithFormula --time=1:30:00 --mem=10G --wrap='{wrapped}'"
            # print(slurm_cmd)
            os.system(slurm_cmd)
            # os.system(cmd)
            # save the result
            # save the formula
            # save the interpolant
            # save the interpolant
    pass

if __name__ == "__main__":
    main()