import os
from utils.paths import *
from count_interpolant_byz3 import count_and_save
from utils.tosmt import cnf_to_smt2_n_way, cnf_to_smt2_def1, cnf_to_smt2_def2, compute_interpolant_def3
import argparse
from utils.utils import generate_cnf, literal_to_expr, clause_to_expr
from utils.interpolant_sanity_check import check_cnf_A_implication
from utils.process_cnf import CNF
from z3 import *
import json
import logging
import time

DEBUG=False

def set_debug(debug):
    global DEBUG
    DEBUG = debug

def prepare_cnf(name,k_value,force_refresh=False):
    logger = logging.getLogger("proofdoor.worker")
    cnf_dir = get_CNF_dir(k_value)
    cnf_path = f"{cnf_dir}/{name}.{k_value}.cnf"
    
    if not os.path.exists(cnf_path):
        logger.info("CNF file %s DNE, regenerating", cnf_path)
        generate_cnf(f"{name}.{k_value}.cnf")
    elif force_refresh:
        logger.info("CNF file %s exists, regenerating due to force_refresh", cnf_path)
        generate_cnf(f"{name}.{k_value}.cnf")
    else:
        logger.info("CNF file %s exists, skipping", cnf_path)

    log_path = f"{cnf_path}.cadicalplain.log"
    drat_path = f"{cnf_path}.cadicalplain.drat"
    # if os.path.exists(drat_path) and os.path.exists(log_path):
    #     return

    solver = "./solvers/cadical"
    extra_flags = "--plain --no-binary"
    cmd = f"{solver} {extra_flags} {cnf_path} {drat_path} > {log_path} 2>&1"
    logger.info("Running command: %s", cmd)
    os.system(cmd)

def prepare_smt_def2(name,k_value,force_refresh=False):
    smt_dir = get_smts_dir(k_value,pddef=2)
    smt_path = f"{smt_dir}/{name}.{k_value}.0.smt2"
    cnf_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cnf"
    if not os.path.exists(smt_path) or force_refresh:
        print(f"SMT file {smt_path} DNE or force_refresh, regenerating")
        cnf_to_smt2_def2(cnf_path,smt_path)

def prepare_interpolant_def3(name,k_value,index,force_refresh=False):
    smt_dir = get_smts_dir(k_value,pddef=3)
    smt_path = f"{smt_dir}/{name}.{k_value}.{index}.smt2"
    interpolant_path = f"{get_interpolant_dir(k_value,pddef=3)}/{name}.{k_value}.{index}.interpolant"
    cnf_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cnf"
    print(f"CNF file path: {cnf_path}")
    if not os.path.exists(interpolant_path) or force_refresh or os.path.getsize(interpolant_path) == 0 or True:
        print(f"Interpolant file {interpolant_path} DNE or force_refresh, regenerating")
        clause_wire_map = compute_interpolant_def3(name, k_value, force_refresh=force_refresh)
        interpolant = clause_wire_map[index]
        
        with open(interpolant_path, "w") as file:
            for line in interpolant:
                for literal in line:
                    file.write(str(literal) + " ")
                file.write(" 0\n")
    else:
        print(f"Interpolant file {interpolant_path} exists, skipping")

def prepare_smt_def1(name,k_value,force_refresh=False):
    smt_dir = get_smt_def1_dir(k_value)
    smt_path = f"{smt_dir}/{name}.{k_value}.0.smt2"
    cnf_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cnf"
    if not os.path.exists(smt_path) or force_refresh:
        print(f"SMT file {smt_path} DNE or force_refresh, regenerating")
        cnf_to_smt2_def1(cnf_path,smt_path)

def compute_strongest_interpolant(name,k_value,index,force_refresh=False, sanity_check=False):
    start_time = time.time()
    cnf_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cnf"
    cnf = CNF(cnf_path, use_cache=True)
    # compute or load the A_local
    # print(f"cnf.iter_map: {cnf.iter_map}")
    # INSERT_YOUR_CODE
    print("CNF done:", time.time() - start_time)
    local_A_variables = cnf.get_variables_local_in_A(index)
    print("local_A_variables done:", time.time())
    # print(f"local_A_variables: {len(local_A_variables)}")
    # exit()
    # construct I_S in SMT format

    smt_definitions = cnf.get_smt_definitions()
    print("smt_definitions done:", time.time() - start_time)
    # for line in smt_definitions:
    #     print(line)
    # print("smt_definitions done")
    A = cnf.get_A(index)
    A_in_smt = A.to_smt()
    print("A_in_smt done:", time.time() - start_time)
    wrapped_assert = ["(assert"] + [f"  {line}" for line in A_in_smt] + [")"]
    smt_source = "\n".join(smt_definitions + wrapped_assert)
    A_in_smt_expression = parse_smt2_string(smt_source)[0]
    print("parse_smt2_string done:", time.time() - start_time)
    print(f"local_A_variables: {len(local_A_variables)}")

    interpolant_path = get_interpolant_dir(k_value,4) + f"/{name}.{k_value}.{index}.interpolant"

    def parse_with_definitions(expr_src):
        smt_input = "\n".join(smt_definitions + [f"(assert {expr_src})"])
        parsed = parse_smt2_string(smt_input)
        if len(parsed) != 1:
            raise ValueError("Expected a single expression from interpolant SMT source")
        return parsed[0]

    IS_expr = None
    IS_sexpr = None
    if not force_refresh and os.path.exists(interpolant_path):
        print(f"Interpolant file {interpolant_path} exists, skipping")
        with open(interpolant_path) as interpolant_file:
            result = json.load(interpolant_file)
        IS_sexpr = result['IS']
        IS_expr = parse_with_definitions(IS_sexpr)
    else:
        print(f"Interpolant file {interpolant_path} DNE or force_refresh, regenerating")
        quantified_vars = {abs(literal) for literal in local_A_variables}
        quantified_bools = [Bool(f"v{var}") for var in sorted(quantified_vars)]
        print("prepare done:", time.time() - start_time)
        quantified_formula = Exists(quantified_bools, A_in_smt_expression)
        print("Exists done:", time.time() - start_time)
        print(quantified_formula.sexpr())
        qe_goal = Tactic('qe')(quantified_formula)
        IS_expr = qe_goal.as_expr()
        IS_sexpr = IS_expr.sexpr()
        print("qe done:", time.time())
        print("*"*100)
        print(IS_sexpr)
        with open(interpolant_path, "w") as interpolant_file:
            json.dump({'IS': IS_sexpr}, interpolant_file)
    # sanity check
    if sanity_check:
        B = cnf.get_B(index)
        B_in_smt = B.to_smt()
        wrapped_B_assert = ["(assert"] + [f"  {line}" for line in B_in_smt] + [")"]
        B_expr = parse_smt2_string("\n".join(smt_definitions + wrapped_B_assert))[0]
        s = Solver()
        s.add(And(A_in_smt_expression, Not(IS_expr)))
        s.add(And(IS_expr, B_expr))
        if s.check() != unsat:
            print("Sanity check failed: interpolant is not between A and B")
        else:
            print(f"A -> IS and IS -> B are valid: {IS_sexpr}")
    return

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
        os.system(f"./bin/z3 {smt_path} > {interpolant_path}")
    elif force_refresh:
        print(f"Interpolant file {interpolant_path} exists, regenerating due to force_refresh")
        os.system(f"./bin/z3 {smt_path} > {interpolant_path}")

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
            os.system(f"./bin/z3 {smt_path} > {interpolant_path}")
        else:
            print(f"Interpolant file {interpolant_path} passed, skipping")
        return failed
    else:
        print(f"Interpolant file {interpolant_path} exists, skipping")
    return True

def prepare_interpolant_cnf(name,k_value,index,force_refresh=False,pddef=0):
    interpolant_cnf_dir = get_interpolant_cnf_dir(k_value,pddef)
    interpolant_cnf_path = f"{interpolant_cnf_dir}/{name}.{k_value}.{index}.smt2.cnf"
    interpolant_dir = get_interpolant_dir(k_value,pddef=pddef) 
    interpolant_path = f"{get_interpolant_dir(k_value,pddef=pddef)}/{name}.{k_value}.{index}.interpolant"
    smt_path = f"{get_smts_dir(k_value,pddef=pddef)}/{name}.{k_value}.{index}.smt2"
    if not os.path.exists(interpolant_cnf_path) or force_refresh:
        print(f"Interpolant CNF file {interpolant_cnf_path} DNE, regenerating")
        count_and_save(interpolant_path,smt_path,-1,pddef)
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
    elif pddef == 3:
        prepare_cnf(name,k_value,force_refresh)
        cnf_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cnf"
        drat_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cadicalplain.drat"
        if not os.path.exists(drat_path) or os.path.getsize(drat_path) == 0:
            print(f"DRAT file {drat_path} DNE, regenerating")
            os.system(f"./solvers/cadical --plain --no-binary {cnf_path} {drat_path}")
        else:
            print(f"DRAT file {drat_path} exists, skipping")

def prepare_interpolant_def1(name,k_value,index,force_refresh=False):
    interpolant_dir = get_interpolant_dir(k_value,pddef=2)
    interpolant_path = f"{interpolant_dir}/{name}.{k_value}.{index}.interpolant"
    cnf_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cnf"
    smt_path = f"{get_smt_def1_dir(k_value)}/{name}.{k_value}.{index}.smt2"
    if index > 0:
        cnf_to_smt2_def2(cnf_path,smt_path,pddef=2,index=index)
    if not os.path.exists(interpolant_path) or force_refresh:
        print(f"Interpolant file {interpolant_path} DNE or force_refresh, regenerating")
        os.system(f"./bin/z3 {smt_path} > {interpolant_path}")
    else:
        print(f"Interpolant file {interpolant_path} exists, skipping")

def prepare_interpolant_def2(name,k_value,index,force_refresh=False):
    interpolant_dir = get_interpolant_dir(k_value,pddef=1)
    interpolant_path = f"{interpolant_dir}/{name}.{k_value}.{index}.interpolant"
    cnf_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cnf"
    smt_path = f"{get_smts_dir(k_value,pddef=2)}/{name}.{k_value}.{index}.smt2"
    if index > 0:
        cnf_to_smt2_def2(cnf_path,smt_path)
    if not os.path.exists(interpolant_path) or force_refresh:
        print(f"Interpolant file {interpolant_path} DNE or force_refresh, regenerating")
        os.system(f"./bin/z3 {smt_path} > {interpolant_path}")
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
        os.system(f"./bin/z3 {smt_path} > {interpolant_path}")
    else:
        print(f"Interpolant file {interpolant_path} exists, skipping")

def prepare_interpolant_only(name,k_value,index,pddef=0,force_refresh=False):
    if pddef == 0:
        prepare_interpolant(name,k_value,index,force_refresh)
    elif pddef == 1:
        prepare_interpolant_def1(name,k_value,index,force_refresh)
        prepare_interpolant_cnf(name,k_value,index,True,pddef=1)
    elif pddef == 2:
        prepare_interpolant_def2(name,k_value,index,force_refresh)
        prepare_interpolant_cnf(name,k_value,index,True,pddef=2)
    elif pddef == 3:
        prepare_interpolant_def3(name,k_value,index,force_refresh)
        # prepare_interpolant_def3(name,k_value,index,force_refresh)
        prepare_interpolant_cnf(name,k_value,index,True,pddef=3)

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
    activate_python = "source .env; source $PYENVPATH"
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
    slurm_out_dir = f"./SlurmLogs/prepare_data_def{pddef}/k_{k_value}/"
    # print(f"python ./scripts/prepare_data.py --name {name} --K {k_value} --pre_interpolant --pddef {pddef}")
    # return
    force_refresh_flag = ""
    if force_refresh:
        force_refresh_flag = "--force_refresh"
    os.makedirs(slurm_out_dir,exist_ok=True)
    id = run_slurm_job_wrap(
        f"python ./scripts/prepare_data.py --name {name} --K {k_value} --pre_interpolant --pddef {pddef} {force_refresh_flag}",
        f"{slurm_out_dir}/{name}.{k_value}.%A_.getsmt.log", f"psmt_{name}.{k_value}",
        time="10:00:00",
        mem="16g"
        )
    for index in range(0, k_value):
        nextid = run_slurm_job_wrap(
            f"python ./scripts/prepare_data.py --name {name} --K {k_value} --index {index} --interpolant_only --pddef {pddef} {force_refresh_flag}",
            f"{slurm_out_dir}/{name}.{k_value}.%A_{index}.prepare_data.log", f"piseq_{name}.{k_value}.{index}",
            wait_id=id,
            time="20:00:00"
            )
        id = nextid

def prepare_all_datas_for_one_smt(name,k_value,index,force_refresh=False):
    activate_python = "source .env; source $PYENVPATH"
    slurm_out_dir = "./SlurmLogs/prepare_data/"
    os.makedirs(slurm_out_dir,exist_ok=True)
    wrapped = f"{activate_python} && python ./scripts/prepare_data.py --name {name} --K {k_value} --index {index}"
    os.system(f"sbatch --job-name=pp_{name}.{k_value}.{index} --output={slurm_out_dir}/{name}.{k_value}.%A_{index}.prepare_data.log --mem=16g --time=20:00:00 --wrap=\"{wrapped}\"")

def prepare_all_datas(name,k_value,force_refresh=False):
    activate_python = "source .env; source $PYENVPATH"
    slurm_out_dir = "./SlurmLogs/prepare_data/"
    os.makedirs(slurm_out_dir,exist_ok=True)
    # wrapped = f"{activate_python} && python ./scripts/prepare_data.py --name {name} --K {k_value} --index \$\SLURM_ARRAY_TASK_ID"
    # os.system(f"sbatch --array=0-{k_value-1} --output={slurm_out_dir}/{name}.{k_value}.%A_%a.prepare_data.log --mem=16g --time=20:00:00 --wrap=\"{wrapped}\"")

def build_cnf_obj(name,k_value):
    cnf_path = f"{get_CNF_dir(k_value)}/{name}.{k_value}.cnf"
    cnf = CNF(cnf_path, use_cache=True)
    print(f"CNF object built for {name}.{k_value}")
    return cnf

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
    parser.add_argument('--build_cnf_obj', action='store_true', help='Build CNF object', required=False)
    parser.add_argument('--pddef', type=int, help='Definition of the interpolant',default=0, required=False)
    parser.add_argument('--debug', action='store_true', help='Debug mode', required=False)
    parser.add_argument('--sanity_check', action='store_true', help='Sanity check', required=False)
    parser.add_argument('--compute_strongest_interpolant', action='store_true', help='Compute strongest interpolant', required=False)
    args = parser.parse_args()

    if args.debug:
        set_debug(True)

    if args.build_cnf_obj:
        build_cnf_obj(args.name,args.K)
        return

    if args.compute_strongest_interpolant:
        compute_strongest_interpolant(args.name,args.K,args.index,sanity_check=args.sanity_check)
        return

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
        # activate_python = "source .env; source $PYENVPATH"
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
