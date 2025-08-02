import os
from utils.paths import *
from count_interpolant_byz3 import count_and_save
from utils.tosmt import cnf_to_smt2_n_way, cnf_to_smt2_def1, cnf_to_smt2_def2
import argparse
from utils.utils import generate_cnf

DEBUG=True

def prepare_cnf(name,k_value,force_refresh=False):
    cnf_dir = get_CNF_dir(k_value)
    cnf_path = f"{cnf_dir}/{name}.{k_value}.cnf"
    if not os.path.exists(cnf_path):
        print(f"CNF file {cnf_path} DNE, regenerating")
        generate_cnf(f"{name}.{k_value}.cnf")
    elif force_refresh:
        print(f"CNF file {cnf_path} exists, regenerating due to force_refresh")
        generate_cnf(f"{name}.{k_value}.cnf")
    else:
        print(f"CNF file {cnf_path} exists, skipping")

def prepare_smt_def1(name,k_value,force_refresh=False):
    smt_dir = get_smt_def1_dir(k_value)
    smt_path = f"{smt_dir}/{name}.{k_value}.0.smt2"
    cnf_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cnf"
    if not os.path.exists(smt_path) or force_refresh:
        print(f"SMT file {smt_path} DNE or force_refresh, regenerating")
        cnf_to_smt2_def1(cnf_path,smt_path)


def prepare_smt(name,k_value,index,force_refresh=False):
    smt_dir = get_smts_dir(k_value)
    smt_path = f"{smt_dir}/{name}.{k_value}.{index}.smt2"
    cnf_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cnf"
    if not os.path.exists(smt_path):
        print(f"SMT file {smt_path} DNE, regenerating")
        cnf_to_smt2_n_way(cnf_path,smt_path)
    elif force_refresh:
        print(f"SMT file {smt_path} exists, regenerating due to force_refresh")
        cnf_to_smt2_n_way(cnf_path,smt_path)
    else:
        print(f"SMT file {smt_path} exists, skipping")

def prepare_interpolant(name,k_value,index,force_refresh=False, check_failed=False):
    interpolant_dir = get_interpolant_dir(k_value)
    interpolant_path = f"{interpolant_dir}/{name}.{k_value}.{index}.interpolant"
    smt_path = f"{get_smts_dir(k_value)}/{name}.{k_value}.{index}.smt2"
    if not os.path.exists(interpolant_path):
        print(f"Interpolant file {interpolant_path} DNE, regenerating")
        os.system(f"./z3 {smt_path} > {interpolant_path}")
    elif force_refresh:
        print(f"Interpolant file {interpolant_path} exists, regenerating due to force_refresh")
        os.system(f"./z3 {smt_path} > {interpolant_path}")

    elif check_failed:
        failed = False
        if os.path.getsize(interpolant_path) == 0:
            failed = True
        else:
            with open(interpolant_path, "r") as file:
                lines = file.readlines()
                if len(lines) < 3 and "error" in lines[0]:
                    failed = True
        if failed:
            smt_path = f"{get_smts_dir(k_value)}/{name}.{k_value}.{index}.smt2"
            print(f"Interpolant file {interpolant_path} failed, regenerating")
            os.system(f"./z3 {smt_path} > {interpolant_path}")
        else:
            print(f"Interpolant file {interpolant_path} passed, skipping")
        return failed
    else:
        print(f"Interpolant file {interpolant_path} exists, skipping")
    return True

def prepare_interpolant_cnf(name,k_value,index,force_refresh=False):
    interpolant_cnf_dir = get_interpolant_cnf_dir()
    interpolant_cnf_path = f"{interpolant_cnf_dir}/{name}.{k_value}.{index}.smt2.cnf"
    interpolant_dir = get_interpolant_dir(k_value) 
    interpolant_path = f"{get_interpolant_dir(k_value)}/{name}.{k_value}.{index}.interpolant"
    smt_path = f"{get_smts_dir(k_value)}/{name}.{k_value}.{index}.smt2"
    if not os.path.exists(interpolant_cnf_path):
        print(f"Interpolant CNF file {interpolant_cnf_path} DNE, regenerating")
        count_and_save(interpolant_path,smt_path,-1)
    else:
        print(f"Interpolant CNF file {interpolant_cnf_path} exists, skipping")

def prepare_for_interpolant_computation(name,k_value,pddef=0,force_refresh=False):
    if pddef == 0:
        prepare_cnf(name,k_value,force_refresh)
        prepare_smt(name,k_value,force_refresh)
    elif pddef == 1:
        prepare_cnf(name,k_value,force_refresh)
        prepare_smt_def1(name,k_value,force_refresh)
    elif pddef == 2:
        prepare_cnf(name,k_value,force_refresh)
        prepare_smt_def2(name,k_value,force_refresh)

def prepare_interpolant_def1(name,k_value,index,force_refresh=False):
    interpolant_dir = get_interpolant_dir(k_value,pddef=2)
    interpolant_path = f"{interpolant_dir}/{name}.{k_value}.{index}.interpolant"
    cnf_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cnf"
    smt_path = f"{get_smt_def1_dir(k_value)}/{name}.{k_value}.{index}.smt2"
    if index > 0:
        cnf_to_smt2_def2(cnf_path,smt_path,pddef=2,index=index)
    if not os.path.exists(interpolant_path) or force_refresh:
        print(f"Interpolant file {interpolant_path} DNE or force_refresh, regenerating")
        os.system(f"./z3 {smt_path} > {interpolant_path}")
    else:
        print(f"Interpolant file {interpolant_path} exists, skipping")

def prepare_interpolant_def1(name,k_value,index,force_refresh=False):
    interpolant_dir = get_interpolant_dir(k_value,pddef=1)
    interpolant_path = f"{interpolant_dir}/{name}.{k_value}.{index}.interpolant"
    cnf_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cnf"
    smt_path = f"{get_smt_def1_dir(k_value)}/{name}.{k_value}.{index}.smt2"
    if index > 0:
        cnf_to_smt2_def1(cnf_path,smt_path)
    if not os.path.exists(interpolant_path) or force_refresh:
        print(f"Interpolant file {interpolant_path} DNE or force_refresh, regenerating")
        os.system(f"./z3 {smt_path} > {interpolant_path}")
    else:
        print(f"Interpolant file {interpolant_path} exists, skipping")

def prepare_interpolant_only(name,k_value,index,pddef=0,force_refresh=False):
    if pddef == 0:
        prepare_interpolant(name,k_value,index,force_refresh)
    elif pddef == 1:
        prepare_interpolant_def1(name,k_value,index,force_refresh)
    elif pddef == 2:
        prepare_interpolant_def2(name,k_value,index,force_refresh)

def prepare_datas(name,k_value,index,force_refresh=False):
    prepare_cnf(name,k_value,force_refresh)
    prepare_smt(name,k_value,index,force_refresh)
    interpolant_failed_before = prepare_interpolant(name,k_value,index,force_refresh,check_failed=True)
    prepare_interpolant_cnf(name,k_value,index,force_refresh or interpolant_failed_before or True)

def run_slurm_job_wrap(cmd, output, job_name,wait_id=None,mem="16g", time="20:00:00"):
    if DEBUG:
        print(f"Running command: {cmd}")
        os.system(cmd)
        return
    activate_python = "source ../general/bin/activate"
    slurm_out_dir = "./SlurmLogs/prepare_data/"
    os.makedirs(slurm_out_dir,exist_ok=True)
    wrap = f"{activate_python} && {cmd}"
    # os.system(f"sbatch --job-name={job_name} --output={output} --mem={mem} --time={time} --wrap=\"{wrap}\"")
    if wait_id is None: 
        full_cmd = f"sbatch --job-name={job_name} --output={output} --mem={mem} --time={time} --wrap=\"{wrap}\""
    else:
        full_cmd = f"sbatch --dependency=afterok:{wait_id} --job-name={job_name} --output={output} --mem={mem} --time={time} --wrap=\"{wrap}\""
    # print(full_cmd)
    job_id = os.popen(full_cmd).read().split()[-1]
    return job_id

def prepare_all_datas_for_one_smt_with_decompose(name,k_value,pddef=1,force_refresh=False):
    slurm_out_dir = f"./SlurmLogs/prepare_data_def{pddef}/"
    # print(f"python ./scripts/prepare_data.py --name {name} --K {k_value} --pre_interpolant --pddef {pddef}")
    # return
    force_refresh_flag = ""
    if force_refresh:
        force_refresh_flag = "--force_refresh"
    os.makedirs(slurm_out_dir,exist_ok=True)
    id = run_slurm_job_wrap(
        f"python ./scripts/prepare_data.py --name {name} --K {k_value} --pre_interpolant --pddef {pddef} {force_refresh_flag}",
        f"{slurm_out_dir}/{name}.{k_value}.%A_.getsmt.log", f"psmt_{name}.{k_value}",
        time="4:00:00",
        mem="8g"
        )
    for index in range(0, k_value):
        nextid = run_slurm_job_wrap(
            f"python ./scripts/prepare_data.py --name {name} --K {k_value} --index {index} --interpolant_only --pddef {pddef} {force_refresh_flag}",
            f"{slurm_out_dir}/{name}.{k_value}.%A_{index}.prepare_data.log", f"piseq_{name}.{k_value}.{index}",
            wait_id=id,
            time="5:00:00"
            )
        id = nextid

def prepare_all_datas_for_one_smt(name,k_value,index,force_refresh=False):
    activate_python = "source ../general/bin/activate"
    slurm_out_dir = "./SlurmLogs/prepare_data/"
    os.makedirs(slurm_out_dir,exist_ok=True)
    wrapped = f"{activate_python} && python ./scripts/prepare_data.py --name {name} --K {k_value} --index {index}"
    os.system(f"sbatch --job-name=pp_{name}.{k_value}.{index} --output={slurm_out_dir}/{name}.{k_value}.%A_{index}.prepare_data.log --mem=16g --time=20:00:00 --wrap=\"{wrapped}\"")

def prepare_all_datas(name,k_value,force_refresh=False):
    activate_python = "source ../general/bin/activate"
    slurm_out_dir = "./SlurmLogs/prepare_data/"
    os.makedirs(slurm_out_dir,exist_ok=True)
    wrapped = f"{activate_python} && python ./scripts/prepare_data.py --name {name} --K {k_value} --index \$\SLURM_ARRAY_TASK_ID"
    os.system(f"sbatch --array=0-{k_value-1} --output={slurm_out_dir}/{name}.{k_value}.%A_%a.prepare_data.log --mem=16g --time=20:00:00 --wrap=\"{wrapped}\"")

def main():
    parser = argparse.ArgumentParser(description='Prepare data for absorption experiments')
    parser.add_argument('--name', type=str, help='Name of the instance', required=True)
    parser.add_argument('--K', type=int, help='k value of the instance', required=True)
    parser.add_argument('--index', type=int, help='index of the interpolant', required=False)
    parser.add_argument('--all', action='store_true', help='Prepare all indexes', required=False)
    parser.add_argument('--force_refresh', action='store_true', help='Force refresh', required=False)
    parser.add_argument('--pre_interpolant', action='store_true', help='Prepare for interpolant computation', required=False)
    parser.add_argument('--interpolant_only', action='store_true', help='Prepare for interpolant computation only', required=False)
    parser.add_argument('--prepare_sequential', action='store_true', help='Prepare for sequential computation', required=False)
    parser.add_argument('--pddef', type=int, help='Definition of the interpolant',default=0, required=False)
    args = parser.parse_args()

    if args.pre_interpolant:
        prepare_for_interpolant_computation(args.name,args.K,force_refresh=args.force_refresh,pddef=args.pddef)
        return

    if args.interpolant_only:
        prepare_interpolant_only(args.name,args.K,args.index,force_refresh=args.force_refresh,pddef=args.pddef)
        return

    if args.prepare_sequential:
        prepare_all_datas_for_one_smt_with_decompose(args.name,args.K,pddef=args.pddef,force_refresh=args.force_refresh)
        return

    if args.all:    
        prepare_all_datas(args.name,args.K,args.force_refresh)
        # activate_python = "source ../general/bin/activate"
        # slurm_out_dir = "./SlurmLogs/prepare_data/"
        # os.makedirs(slurm_out_dir,exist_ok=True)
        # for index in range(args.K):
        #     wrapped = f"{activate_python} && python ./scripts/utils/prepare_data.py --name {args.name} --K {args.K} --index \$\SLURM_ARRAY_TASK_ID"
        #     os.system(f"sbatch --array=0-{args.K-1} --output={slurm_out_dir}/{args.name}.{args.K}.{index}.prepare_data.log --mem=10g --time=20:00:00 --wrap=\"{wrapped}\"")
        return

    prepare_datas(args.name,args.K,args.index,args.force_refresh)
    pass

if __name__ == "__main__":
    main()