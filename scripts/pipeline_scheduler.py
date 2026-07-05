#!/usr/bin/env python3
"""
三阶段调度器（interpolants -> SMT→CNF -> absorption），按 (instance, K, index) 细粒度管理依赖：

1. interpolants：
   - 扫描所有 K 个 interpolant 文件，区分 ok / missing / empty / error / timeout（timeout 通过本脚本自己的 log 判断）。
   - 对于从未尝试过的 missing/empty index，按 index 顺序提交一串有 afterok 依赖的 Slurm job，
     每个 job 调用 `prepare_single.py --interpolant_only` 来计算对应 interpolant。
   - 对于 timeout/error 的 index 不自动重试，整条 pipeline 跳过该 index。
2. SMT→CNF：
   - 对每个 index 独立判断：若 cnf 缺失/空且该 index 的 interpolant 不是 timeout/error，
     则提交一个 SMT→CNF job，必要时依赖本轮对应的 interpolant job（afterok）。
3. absorption：
   - 若 Dashboard 中 absorption 结果还不是 success，则在本轮所有 SMT→CNF job 完成之后（afterany 依赖）提交一个
     `AbsorptionExperiment.py --K K --main --force_instance instance` 的 job，让它自己按内部逻辑检查哪些 index 可用。

该脚本是幂等的：可以多次运行，它只会为“当前缺的、且本脚本尚未尝试过”的部分补 job。
"""

import argparse
import json
import os
import csv
import pandas as pd
import subprocess
from utils.paths import get_interpolant_cnf_dir
from pathlib import Path
from typing import Dict, Tuple, List, Optional
from utils.scramble import ScrambleType, SCRAMBLE_TYPES, PERMUTE_LIMIT
# 这些 import 复用你现有的路径工具和 Dashboard 约定
from utils.paths import (
    get_CNF_dir,
    get_interpolant_dir,
    get_interpolant_cnf_dir,
    get_latest_PDC_result,
    get_latest_absorption_result,
)
from utils.catagory import get_instance_list
from utils.utils import get_python_activate_command

# ----------------- 全局配置（按需改） -----------------

# 和 dumb_sceduler.sh 中的 target_list 对应
DEFAULT_TARGET_INSTANCES = [
    # "cal123",
    # "cal142",
    # "6s428",
    # "6s339rb19",
    # "6s31",
    # "6s119",
    # "6s194",
    # "beemandrsn4b1",
    "6s329rb19",
    "6s329rb20",
    "6s357r"
]
INSTANCE_K_MAP = {
    # "cal123": 3,
    # "cal142": 2,
    # "6s428": 4,
    # "6s339rb19": 25,
    # "6s31": 24,
    # "6s119": 38,
    # "6s194": 51,
    # "beemandrsn4b1": 6,
    "6s329rb19": 10,
    "6s329rb20": 10,
    "6s357r": 23,
}
TEST_TARGET_INSTANCES = [
    "139442p0"
]
# 你现在常用的 K 集合
DEFAULT_K_LIST = [10, 15, 20, 25, 30, 35, 40, 45, 50]
TEST_K_LIST = [3, 4, 5,6,7,8,9]
# interpolant 定义：你现在主要用 def1
PDDEF = 1

# 每个 K,i 的 job 的时间和内存
TIME_PER_JOB = "20:00:00"
MEM_INTERP = "32g"
MEM_SMT2CNF = "32g"
MEM_ABSORPTION = "64g"
MEM_PREPARE_FORMULA = "32g"
TIME_PREPARE_FORMULA = "20:00:00"

class status:
    done = "done"
    not_started = "not started"
    partial = "partial"
    failed = "failed"

# ----------------- 一些工具函数 -----------------

def run_cmd(cmd: str) -> str:
    """运行 shell 命令，返回 stdout.strip()，并打印命令方便 debug。"""
    print(f"[CMD] {cmd}")
    out = subprocess.check_output(cmd, shell=True, text=True)
    return out.strip()


def sbatch_wrap(
    inner_cmd: str,
    time_limit: str,
    mem: str,
    output_log: str,
    job_name: str,
    dependency: str = None,
    cpus: int = 1,
) -> str:
    """
    提交一个 sbatch --wrap job，返回 job id。
    inner_cmd 不需要自己激活 venv，这里统一包一层。
    """
    os.makedirs(os.path.dirname(output_log), exist_ok=True)
    pycmd = get_python_activate_command()
    wrapped = f'{pycmd} && {inner_cmd}'
    dep_part = f" --dependency=afterok:{dependency}" if dependency else ""
    cmd = (
        f"sbatch --job-name={job_name} --time={time_limit} --mem={mem} "
        f"--cpus-per-task={cpus} --output={output_log}{dep_part} "
        f'--wrap="{wrapped}"'
    )
    out = run_cmd(cmd)
    # "Submitted batch job 123456"
    return out.split()[-1]


# ----------------- 阶段 1：检查 / 提交 interpolant（顺序计算） -----------------

def _perm_suffix(permute: Optional[str], permute_index: int) -> str:
    return f".perm_{permute}_{permute_index}" if permute else ""

def was_interpolant_attempted(
    instance: str,
    K: int,
    index: int,
    pddef: int = PDDEF,
    reverse: bool = False,
    permute: Optional[str] = None,
    permute_index: int = 0,
) -> bool:
    """
    通过 **本调度器自己的 per-index 日志** 判断某个 interpolant 是否“尝试过计算”（可能是 timeout / 被杀掉）。
    只要这些 log 里出现过 `<instance>.<K>.<index>.interpolant` 就认为尝试过。
    """
    perm_suffix = _perm_suffix(permute, permute_index)
    suffix = ".reverse.interpolant" if reverse else ".interpolant"
    name_fragment = f"{instance}.{K}.{index}{perm_suffix}{suffix}"

    # 只看新调度器自己的 per-index 日志
    logs_root = f"./SlurmLogs/prepare_interpolants_def{pddef}/k_{K}"
    if os.path.isdir(logs_root):
        for fname in os.listdir(logs_root):
            if f"{instance}.{K}" not in fname:
                continue
            if not fname.endswith(f"_{index}.prepare.log"):
                continue
            log_path = os.path.join(logs_root, fname)
            try:
                with open(log_path, "r") as f:
                    if name_fragment in f.read():
                        return True
            except OSError:
                continue

    return False

def classify_single_interpolant(path: str) -> str:
    """
    返回单个 interpolant 文件的状态：
    - 'missing': 不存在
    - 'empty'  : 文件存在但 size=0
    - 'error'  : 第一行包含 'error'
    - 'ok'     : 看起来正常
    """
    if not os.path.exists(path):
        return "missing"
    if os.path.getsize(path) == 0:
        return "empty"
    with open(path, "r") as f:
        first = f.readline().strip().lower()
    # Z3 may print only a status line when no interpolant exists (e.g. "sat"/"unknown").
    if first in ("sat", "unknown"):
        return "error"
    if "error" in first:
        return "error"
    return "ok"


def classify_interpolants(
    instance: str,
    K: int,
    pddef: int = PDDEF,
    reverse: bool = False,
    permute: Optional[str] = None,
    permute_index: int = 0,
) -> Tuple[str, Dict[int, str]]:
    """
    检查某个 (instance, K) 的 K 个 interpolant 文件。
    返回:
    - overall_status: 'none' | 'partial' | 'done' | 'failed'
    - per_index: {index -> 'missing'|'empty'|'error'|'ok'}
    """
    base = get_interpolant_dir(K, pddef)
    perm_suffix = _perm_suffix(permute, permute_index)
    per_index: Dict[int, str] = {}
    has_ok = False
    has_unattempted_missing_or_empty = False
    has_failed = False  # 包括 error 和 timeout 这类“尝试过但没成”

    for i in range(K):
        if reverse:
            path = os.path.join(base, f"{instance}.{K}.{i}{perm_suffix}.reverse.interpolant")
        else:
            path = os.path.join(base, f"{instance}.{K}.{i}{perm_suffix}.interpolant")
        st = classify_single_interpolant(path)

        if st in ("missing", "empty"):
            # 需要区分：从未尝试 vs. 曾经尝试（timeout/kill 等）
            if was_interpolant_attempted(
                instance,
                K,
                i,
                pddef,
                reverse=reverse,
                permute=permute,
                permute_index=permute_index,
            ):
                # 视为“尝试过但失败”（可能是 timeout）
                st = "timeout"
                has_failed = True
            else:
                has_unattempted_missing_or_empty = True
        elif st == "error":
            has_failed = True
        elif st == "ok":
            has_ok = True

        per_index[i] = st

    if has_failed:
        overall = "failed"
    elif has_unattempted_missing_or_empty and not has_ok:
        overall = "none"
    elif has_unattempted_missing_or_empty and has_ok:
        overall = "partial"
    else:
        overall = "done"
    return overall, per_index


def submit_compute_interpolants_job(
    instance: str,
    K: int,
    per_index: Dict[int, str],
    pddef: int = PDDEF,
    reverse: bool = False,
    permute: Optional[str] = None,
    permute_index: int = 0,
    force_refresh: bool = False,
) -> Dict[int, str]:
    """
    提交一串有依赖关系的 slurm job，顺序计算 (instance, K) 的所有“尚未成功”的 interpolants。

    要求：
    - 对于已经是 'ok' 的 index 不重复计算；
    - 对于 'missing' / 'empty' 的 index，按照从小到大的顺序，
      每个 (instance, K, i) 一个 job，并使用 --dependency=afterok
      确保这些 job 在同一次调度中按 index 递增的顺序执行。

    具体每个 job 内部做的事情等价于：
        python ./scripts/prepare_single.py --name <instance> --K <K> --index <i> --interpolant_only --pddef <pddef> --force_refresh
    """
    logs_dir = f"./SlurmLogs/prepare_interpolants_def{pddef}/k_{K}"
    os.makedirs(logs_dir, exist_ok=True)

    last_job_id = None
    job_ids: Dict[int, str] = {}
    perm_suffix = _perm_suffix(permute, permute_index)
    permute_flag = f"--permute {permute} --permute_index {permute_index}" if permute else ""

    # pddef=3 ("proofgate") interpolants are generated for *all indices at once*
    # by `prepare_single.prepare_interpolant_def3`, so we must not schedule one job
    # per index (that would race and overwrite outputs).
    if pddef == 3:
        if reverse:
            raise ValueError("pddef=3/proofgate does not support --reverse")
        need = force_refresh or any(st in ("missing", "empty") for st in per_index.values())
        if not need:
            print(f"[{instance}.{K}] pddef=3 interpolants already present; skip scheduling.")
            return {}

        job_name = f"interp_def3_{instance}.{K}{perm_suffix}"
        log_path = f"{logs_dir}/{instance}.{K}{perm_suffix}.%A_all.prepare.log"
        force_refresh_flag = "--force_refresh" if force_refresh else ""
        # Run pre-interpolant (CNF/DRAT prep) then interpolant generation in the same job.
        inner_cmd = (
            f"python ./scripts/prepare_single.py --name {instance} --K {K} "
            f"--pre_interpolant --pddef 3 {force_refresh_flag} && "
            f"python ./scripts/prepare_single.py --name {instance} --K {K} "
            f"--interpolant_only --pddef 3 {force_refresh_flag}"
        )
        last_job_id = sbatch_wrap(
            inner_cmd,
            time_limit=TIME_PER_JOB,
            mem=MEM_INTERP,
            output_log=log_path,
            job_name=job_name,
            dependency=last_job_id,
        )
        # Provide per-index dependencies for downstream stage-2 jobs.
        for i in range(K):
            job_ids[i] = last_job_id
        return job_ids

    # IMPORTANT:
    # - forward(pddef=1): index i may depend on interpolant (i-1)
    # - reverse(pddef=1): index i may depend on interpolant (i+1)
    # so the safe scheduling order must follow the dependency direction.
    #
    # Also, interpolant generation generally depends on the CNF/SMT prep. We submit
    # a single `--pre_interpolant` job up front so per-index jobs don't fail when
    # inputs are missing.
    if force_refresh or any(st in ("missing", "empty") for st in per_index.values()):
        prep_job_name = f"prep_interp_{instance}.{K}{perm_suffix}{'.rev' if reverse else ''}"
        prep_log = f"{logs_dir}/{instance}.{K}{perm_suffix}{'.reverse' if reverse else ''}.%A_prep.prepare.log"
        reverse_flag = "--reverse" if reverse else ""
        force_refresh_flag = "--force_refresh" if force_refresh else ""
        prep_cmd = (
            f"python ./scripts/prepare_single.py "
            f"--name {instance} --K {K} "
            f"--pre_interpolant --pddef {pddef} {force_refresh_flag} {reverse_flag} {permute_flag}"
        )
        last_job_id = sbatch_wrap(
            prep_cmd,
            time_limit=TIME_PER_JOB,
            mem=MEM_INTERP,
            output_log=prep_log,
            job_name=prep_job_name,
            dependency=last_job_id,
        )

    indices = range(K - 1, -1, -1) if reverse else range(K)
    for i in indices:
        status = per_index.get(i, "missing")
        # 默认模式：只对“从未尝试过的 missing/empty” 提交补算；timeout/error 交给人工查看
        if not force_refresh:
            if status in ("timeout", "error"):
                # 后续 index 会依赖这个失败点，继续提交也只会失败/浪费资源
                print(f"[{instance}.{K}.{i}] interpolant is {status}; stop scheduling dependent indices")
                break
            if status not in ("missing", "empty"):
                print(f"[{instance}.{K}.{i}] interpolant already computed or failed, skip")
                continue
        job_name = f"interp_{instance}.{K}.{i}{perm_suffix}{'.rev' if reverse else ''}"
        log_path = f"{logs_dir}/{instance}.{K}{perm_suffix}{'.reverse' if reverse else ''}.%A_{i}.prepare.log"
        reverse_flag = "--reverse" if reverse else ""
        force_refresh_flag = "--force_refresh" if force_refresh else ""
        inner_cmd = (
            f"python ./scripts/prepare_single.py "
            f"--name {instance} --K {K} --index {i} "
            f"--interpolant_only --pddef {pddef} {force_refresh_flag} {reverse_flag} {permute_flag}"
        )
        last_job_id = sbatch_wrap(
            inner_cmd,
            time_limit=TIME_PER_JOB,
            mem=MEM_INTERP,
            output_log=log_path,
            job_name=job_name,
            dependency=last_job_id,
        )
        job_ids[i] = last_job_id

    return job_ids


# ----------------- 阶段 2：SMT → CNF -----------------

def classify_smt_cnf(
    instance: str,
    K: int,
    pddef: int = PDDEF,
    reverse: bool = False,
    permute: Optional[str] = None,
    permute_index: int = 0,
) -> Tuple[str, Dict[int, str]]:
    """
    类似地检查 smtcnf 文件：
    - 'missing' / 'empty' / 'ok'
    """
    base = get_interpolant_cnf_dir(K, pddef)
    perm_suffix = _perm_suffix(permute, permute_index)
    per_index: Dict[int, str] = {}
    has_ok = False
    has_missing_or_empty = False

    for i in range(K):
        if reverse:
            path = os.path.join(base, f"{instance}.{K}.{i}{perm_suffix}.reverse.smtcnf")
        else:
            path = os.path.join(base, f"{instance}.{K}.{i}{perm_suffix}.smtcnf")
        if not os.path.exists(path):
            st = "missing"
        elif os.path.getsize(path) == 0:
            st = "empty"
        else:
            st = "ok"
        per_index[i] = st
        if st == "ok":
            has_ok = True
        elif st in ("missing", "empty"):
            has_missing_or_empty = True

    if has_missing_or_empty and not has_ok:
        overall = "none"
    elif has_missing_or_empty and has_ok:
        overall = "partial"
    else:
        overall = "done"
    return overall, per_index


def get_smt_cnf_status(instance: str, K: int, pddef: int = PDDEF) -> str:
    """
    获取 SMT→CNF 的整体状态，只返回 overall（'none'/'partial'/'done'）。
    """
    overall, _ = classify_smt_cnf(instance, K, pddef)
    return overall


# 兼容旧名字
get_smtcnf_status = get_smt_cnf_status


def submit_smt_to_cnf_jobs(
    instance: str,
    K: int,
    interp_status: Dict[int, str],
    interp_job_ids: Dict[int, str],
    cnf_per_index: Dict[int, str],
    pddef: int = PDDEF,
    reverse: bool = False,
    permute: Optional[str] = None,
    permute_index: int = 0,
    force_refresh: bool = False,
) -> Dict[int, str]:
    """
    为所有需要的 index 提交 SMT→CNF 任务：
    - 若某 index 的 interpolant 是 'timeout'/'error'，跳过该 index；
    - 若 smtcnf 已经是 ok，则不重复；
    - 若 interpolant 需要在本次补算，则 smt2cnf 依赖对应的 interpolant job；
      否则直接提交，无依赖。
    返回 {index -> smt2cnf_job_id}。
    """
    logs_dir = f"./SlurmLogs/smt_to_cnf_def{pddef}/k_{K}"
    os.makedirs(logs_dir, exist_ok=True)

    smt_job_ids: Dict[int, str] = {}
    perm_suffix = _perm_suffix(permute, permute_index)
    permute_flag = f"--permute {permute} --permute_index {permute_index}" if permute else ""
    for i in range(K):
        istatus = interp_status.get(i, "missing")
        # 对于明确失败 / timeout 的 index，整个 pipeline 跳过该 index
        if (not force_refresh) and istatus in ("timeout", "error"):
            continue

        cnf_status = cnf_per_index.get(i, "missing")
        if cnf_status == "ok" and not force_refresh:
            continue

        job_name = f"smt2cnf_{instance}.{K}.{i}{perm_suffix}"
        log_path = f"{logs_dir}/{instance}.{K}{perm_suffix}.%A_{i}.log"
        reverse_flag = "--reverse" if reverse else ""
        if pddef == 3:
            if reverse:
                raise ValueError("pddef=3/proofgate does not support --reverse")
            force_refresh_flag = "--force_refresh" if force_refresh else ""
            inner_cmd = (
                f"python scripts/ProofGateInterpolantToSMTCNF.py "
                f"--instance {instance} --K {K} --index {i} {force_refresh_flag}"
            )
        else:
            inner_cmd = (
                f"python scripts/SMTTranslationToCNFExperiment.py "
                f"--instance {instance} --K {K} --index {i} {reverse_flag} {permute_flag}"
            )

        dependency = None
        # 如果本轮提交了 interpolant job，则 smt2cnf 依赖对应 interpolant job
        if force_refresh and i in interp_job_ids:
            dependency = interp_job_ids[i]
        elif istatus in ("missing", "empty") and i in interp_job_ids:
            dependency = interp_job_ids[i]

        job_id = sbatch_wrap(
            inner_cmd,
            time_limit=TIME_PER_JOB,
            mem=MEM_SMT2CNF,
            output_log=log_path,
            job_name=job_name,
            dependency=dependency,
        )
        smt_job_ids[i] = job_id

    return smt_job_ids


# ----------------- 阶段 3：Absorption -----------------

def load_json_if_exists(path: str):
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def get_absorption_status(instance: str, K: int) -> str:
    """
    读取 absorption Dashboard：
    - 返回 'success' / 'error' / 'not started' / 'WIP' / ...
    """
    path = get_latest_absorption_result(K)
    report = load_json_if_exists(path)
    if not report or instance not in report:
        return "not started"
    return report[instance].get("absorptionstatus", "not started")


def submit_absorption_job(
    instance: str,
    K: int,
    category: str = None,
    dependency_job_ids: Optional[List[str]] = None,
    reverse: bool = False,
    interpolant_pddef: int = PDDEF,
    permute: Optional[str] = None,
    permute_index: int = 0,
) -> None:
    """
    为单个 (instance, K) 提交 absorption 管理 job：
    它内部会像 AbsorptionExperiment.manage 一样再往 slurm 扔一批子 job。
    """
    logs_dir = f"./SlurmLogs/absorption_manage/k_{K}"
    os.makedirs(logs_dir, exist_ok=True)
    log_path = f"{logs_dir}/AbsorptionManage.{instance}.{K}.%j.log"
    job_name = f"absorb_manage_{instance}.{K}"

    category_flag = f"--category {category}" if category else ""
    reverse_flag = "--reverse" if reverse else "--no_reverse"
    permute_flag = f"--permute {permute} --permute_index {permute_index}" if permute else ""
    pddef_flag = "" if interpolant_pddef == 1 else f"--interpolant_pddef {interpolant_pddef}"
    inner_cmd = (
        f"python scripts/AbsorptionExperiment.py "
        f"--K {K} --main --force_instance {instance} {category_flag} {reverse_flag} {pddef_flag} {permute_flag}"
    )

    # 构造依赖：在所有 smt2cnf jobs 完成后再启动（允许部分失败，因此用 afterany）
    dep_part = ""
    if dependency_job_ids:
        deps = ":".join(dependency_job_ids)
        dep_part = f" --dependency=afterany:{deps}"
    pycmd = get_python_activate_command()

    wrapped = f"{pycmd} && {inner_cmd}"
    cmd = (
        f"sbatch --job-name={job_name} --time={TIME_PER_JOB} --mem={MEM_ABSORPTION} "
        f"--cpus-per-task=4 --output={log_path}{dep_part} --wrap=\"{wrapped}\""
    )
    run_cmd(cmd)

def submit_prepare_formula_jobs(
    names: List[str],
    use_summary: str = "regression_summary.csv",
    category: Optional[str] = None,
) -> None:
    """
    为 regression_summary 中每个 name 提交一个 Slurm 任务：生成 K=2..20 的 formula，
    用 CaDiCaL 顺序求解（保留 proof），超时 1600s 则终止后续求解，最后写 info JSON。
    每任务 32G 内存、20h 时间。
    """
    logs_dir = "./SlurmLogs/prepare_formula"
    os.makedirs(logs_dir, exist_ok=True)
    for name in names:
        job_name = f"prep_formula_{name}"
        log_path = f"{logs_dir}/{name}.%j.log"
        inner_cmd = f"python scripts/prepare_formula_single.py --name {name}"
        job_id = sbatch_wrap(
            inner_cmd,
            time_limit=TIME_PREPARE_FORMULA,
            mem=MEM_PREPARE_FORMULA,
            output_log=log_path,
            job_name=job_name,
            dependency=None,
        )
        print(f"[prepare_formula] Submitted {name} -> job {job_id}")


def prepare_all_formula_interpolants(
    instance_k_map: Dict[str, int],
    k_limit: int = 10,
    pddef: int = PDDEF,
    reverse: bool = False,
    permute: Optional[str] = None,
    permute_index: int = 0,
    force_refresh: bool = False,
) -> None:
    """
    为 regression_summary 中每个 (name, K) 补齐 interpolants（仅调度 interpolant 相关 job）。

    行为：
    - 对每个 name，遍历 K=2..min(local_max_k, k_limit)；
    - 先检查 interpolants 是否整体 done；
    - 若未 done，则按本调度器的核心逻辑提交 Slurm jobs（等价于 schedule_for_instance 的 stage-1）。

    说明：
    - 默认只补算从未成功的 missing/empty；timeout/error 默认跳过（除非 force_refresh=True）。
    - k_limit 目前按需求先固定默认 10。
    """
    if k_limit < 2:
        print(f"[prepare_all_formula_interpolants] k_limit={k_limit} < 2; nothing to do.")
        return

    total_checked = 0
    total_scheduled = 0
    for name, local_max_k in instance_k_map.items():
        if local_max_k is None:
            continue
        try:
            local_max_k_int = int(local_max_k)
        except Exception:
            continue
        max_k = min(local_max_k_int, k_limit)
        if max_k < 2:
            continue

        for K in range(max_k, max_k + 1):
            total_checked += 1
            overall, per_index = classify_interpolants(
                name,
                K,
                pddef=pddef,
                reverse=reverse,
                permute=permute,
                permute_index=permute_index,
            )
            if overall == "done" and not force_refresh:
                continue
            if overall == "failed" and not force_refresh:
                # 默认不自动重算 error/timeout（避免无限重提），除非显式 force_refresh
                print(f"[prepare_all_formula_interpolants] [{name}.{K}] interpolants status=failed; skip (use --force_refresh to override).")
                continue

            print(f"[prepare_all_formula_interpolants] [{name}.{K}] interpolants status={overall}; scheduling missing/empty (k_limit={k_limit}).")
            job_ids = submit_compute_interpolants_job(
                name,
                K,
                per_index,
                pddef=pddef,
                reverse=reverse,
                permute=permute,
                permute_index=permute_index,
                force_refresh=force_refresh,
            )
            if job_ids:
                total_scheduled += 1

    print(
        f"[prepare_all_formula_interpolants] Done. checked={total_checked}, scheduled_instances={total_scheduled}, "
        f"k_limit={k_limit}, pddef={pddef}, reverse={reverse}, permute={permute}, permute_index={permute_index}, force_refresh={force_refresh}"
    )


def check_instance_status(instance: str, K: int, pddef: int = PDDEF) -> str:
    """
    汇总某个 (instance, K) 的整体进度，返回简要字符串：
    - interpolants: overall(count_ok/K)
    - smt2cnf     : overall(count_ok/K)
    - absorption  : dashboard status
    """
    # Interpolants
    interp_overall, interp_per_index = classify_interpolants(instance, K, pddef)
    num_interp_ok = sum(1 for st in interp_per_index.values() if st == "ok")

    # SMT → CNF
    cnf_overall, cnf_per_index = classify_smt_cnf(instance, K, pddef)
    num_cnf_ok = sum(1 for st in cnf_per_index.values() if st == "ok")

    # Absorption (dashboard)
    absorp_status = get_absorption_status(instance, K)

    return (
        f"interpolants:{interp_overall}({num_interp_ok}/{K}), "
        f"smt2cnf:{cnf_overall}({num_cnf_ok}/{K}), "
        f"absorption:{absorp_status}"
    )

# ----------------- 主调度逻辑 -----------------

def schedule_for_instance(
    instance: str,
    K: int,
    pddef: int = PDDEF,
    category: str = None,
    reverse: bool = False,
    interpolation: bool = False,
    permute: Optional[str] = None,
    permute_index: int = 0,
    do_absorption: bool = False,
    force_refresh: bool = False,
) -> None:
    print(f"=== Scheduling pipeline for {instance}, K={K}, pddef={pddef} ===")
    # return
    # 0) K 已在上游选定（summary/映射），此处直接使用

    # 1) interpolants：按 index 细粒度调度
    interp_overall, interp_per_index = classify_interpolants(
        instance,
        K,
        pddef,
        reverse=reverse,
        permute=permute,
        permute_index=permute_index,
    )
    print(f"[{instance}.{K}] Interpolants status: {interp_overall}")
    # 在 force_refresh 下，即便当前状态是 failed，也应该重算，而不是直接跳过
    interp_job_ids: Dict[int, str] = {}
    if interp_overall == "failed" and not force_refresh:
        print(f"[{instance}.{K}] Some interpolants failed (error/timeout); will skip those indices but continue for others.")
        return

    # 为所有尚未尝试的 missing/empty index 提交顺序 interpolant jobs
    counts = {}
    for st in interp_per_index.values():
        counts[st] = counts.get(st, 0) + 1
    print(f"[{instance}.{K}] Interpolant counts: {counts}")
    # force_refresh 或 interpolation 模式：提交 interpolant 计算（force_refresh 时会覆盖所有 index）
    if force_refresh or interpolation:
        interp_job_ids = submit_compute_interpolants_job(
            instance,
            K,
            interp_per_index,
            pddef,
            reverse=reverse,
            permute=permute,
            permute_index=permute_index,
            force_refresh=force_refresh,
        )
        if interpolation:
            return
    # 1.5) 输出该 instance 的完成情况
    # num_ok = sum(1 for st in interp_per_index.values() if st == "ok")
    # print(f"[{instance}.{K}] Interpolants ok: {num_ok}/{K}")

    # 2) SMT→CNF：对所有index都ok的Interpolant提交smt2cnf job
    cnf_overall, cnf_per_index = classify_smt_cnf(
        instance,
        K,
        pddef,
        reverse=reverse,
        permute=permute,
        permute_index=permute_index,
    )
    print(f"[{instance}.{K}] SMT→CNF status: {cnf_overall}, interp_per_index: {interp_per_index}")
    print(f"[{instance}.{K}] Submitting SMT→CNF jobs where needed (possibly with dependency on interpolant jobs).")
    smt_job_ids = {}
    if force_refresh:
        # 强制重算：即便某些 index 之前是 error/timeout，也允许继续尝试（由 Z3/资源决定）
        smt_job_ids = submit_smt_to_cnf_jobs(
            instance,
            K,
            interp_per_index,
            interp_job_ids,
            cnf_per_index,
            pddef,
            reverse=reverse,
            permute=permute,
            permute_index=permute_index,
            force_refresh=True,
        )
    else:
        ok_only_interp = {i: st for i, st in interp_per_index.items() if st == "ok"}
        if not ok_only_interp:
            print(f"[{instance}.{K}] No 'ok' interpolants; skip SMT→CNF submission for now.")
        else:
            smt_job_ids = submit_smt_to_cnf_jobs(
                instance,
                K,
                ok_only_interp,
                {},
                cnf_per_index,
                pddef,
                reverse=reverse,
                permute=permute,
                permute_index=permute_index,
                force_refresh=False,
            )

    # 3) absorption：按需启动（默认不跑，避免误发大量 job）
    if do_absorption:
        absorp_status = get_absorption_status(instance, K)
        print(f"[{instance}.{K}] Absorption dashboard: {absorp_status}")
        if absorp_status == "success":
            print(f"[{instance}.{K}] Absorption already success, skip.")
            return
        print(f"[{instance}.{K}] Submitting absorption job (dependent on all scheduled SMT→CNF jobs, if any).")
        submit_absorption_job(
            instance,
            K,
            category=category,
            dependency_job_ids=list(smt_job_ids.values()) if smt_job_ids else None,
            reverse=reverse,
            interpolant_pddef=pddef,
            permute=permute,
            permute_index=permute_index,
        )

def get_proofdoor_size(instance: str, K: int, pddef: int = PDDEF) -> int:
    interpolant_sizes = []
    base_dir = get_interpolant_cnf_dir(K, pddef)
    for i in range(K):
        smtcnf_path = os.path.join(base_dir, f"{instance}.{K}.{i}.smtcnf")
        assert os.path.exists(smtcnf_path) and os.path.getsize(smtcnf_path) > 0, (
            f"[{instance}.{K}.{i}] smtcnf file not found or empty"
        )

        with open(smtcnf_path, "r") as f:
            size = 0
            for line in f:
                line = line.strip()
                if not line or line.startswith("c") or line.startswith("p "):
                    continue
                size += 1
        interpolant_sizes.append(size)
    return sum(interpolant_sizes)


def get_formula_size(instance: str, K: int) -> int:
    """
    读取原始 CNF 公式的子句数量（优先使用 header，缺失则按行数统计）。
    """
    cnf_path = os.path.join(get_CNF_dir(K), f"{instance}.{K}.cnf")
    if not os.path.exists(cnf_path) or os.path.getsize(cnf_path) == 0:
        raise FileNotFoundError(f"[{instance}.{K}] CNF file not found or empty: {cnf_path}")

    header_count = None
    clauses = 0
    with open(cnf_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("c"):
                continue
            if line.startswith("p cnf"):
                parts = line.split()
                if len(parts) >= 4 and parts[3].isdigit():
                    header_count = int(parts[3])
                continue
            if line.endswith(" 0") or line.endswith("\t0") or line == "0":
                clauses += 1

    return header_count if header_count is not None else clauses


def check_pds_ratio(instance_k_map: Dict[str, int], pddef: int = PDDEF) -> None:
    pds_sizes = {}
    formula_sizes = {}
    ratios = []
    for instance, K in instance_k_map.items():
        # print(f"[{instance}.{K}] Checking PDS ratio, smt2cnf status: {get_smt_cnf_status(instance, K)}")
        if get_smt_cnf_status(instance, K, pddef=pddef) == status.done:
            # print("matched")
            pds_sizes[instance] = get_proofdoor_size(instance, K, pddef=pddef)
            formula_sizes[instance] = get_formula_size(instance, K)
            ratios.append(pds_sizes[instance] / formula_sizes[instance])

    if not ratios:
        print("No instances with completed SMT→CNF; ratio not computed.")
        return None

    average_ratio = sum(ratios) / len(ratios)
    for instance in pds_sizes.keys():
        print(f"{instance} {pds_sizes[instance]} {formula_sizes[instance]} {pds_sizes[instance] / formula_sizes[instance]}")
    print(f"Average PDS size: {sum(pds_sizes.values()) / len(pds_sizes)}")
    print(f"Average formula size: {sum(formula_sizes.values()) / len(formula_sizes)}")
    print(f"Average ratio: {average_ratio}")
    return average_ratio

def output_status_to_csv(
    category: str,
    reverse: bool = False,
    permute: Optional[str] = None,
    permute_index: int = 0,
    scaling: bool = False,
    pddef: int = PDDEF,
):
    # 生成 CSV：
    # - scaling=False: 每个 instance 只输出 local_max_k 的一行（保持兼容现有 category*.csv 用法）
    # - scaling=True : 对每个 instance 输出 K=1..local_max_k-1 的多行（与 --scaling 调度逻辑一致）
    rows: List[Dict[str, str]] = []
    summary_df = pd.read_csv("regression_summary.csv")

    required_cols = {"instance_name", "local_max_k", "best_model"}
    missing = required_cols - set(summary_df.columns)
    if missing:
        raise ValueError(f"summary CSV 缺少必要列: {sorted(missing)}")

    # filtered = summary_df[(summary_df["best_model"] == "linear") or (summary_df["best_model"] == "exponential")]
    filtered = summary_df[summary_df["best_model"] == category]
    # filtered = summary_df[summary_df["best_model"] == "linear"]
    instance_k_map = dict(zip(filtered["instance_name"], filtered["local_max_k"]))
    category_map = dict(zip(filtered["instance_name"], filtered["best_model"]))
    instance_k_map = dict(sorted(instance_k_map.items()))
    perm_suffix = _perm_suffix(permute, permute_index)

    def normalize_status(s: str) -> str:
        if s == "done":
            return "done"
        if s == "none":
            return "none"
        # 将 'partial' / 'failed' 等其它状态都归并为 'partial'
        return "partial"

    instances = list(instance_k_map.keys())
    if permute:
        # 和 main() 的调度逻辑保持一致：scramble 只跑前若干个实例
        instances = instances[:PERMUTE_LIMIT]

    for instance in instances:
        # schedule_for_instance(instance, int(instance_k_map[instance]))
        K = int(instance_k_map[instance])

        k_values = range(1, K) if scaling else [K]
        for stepK in k_values:
            interp_overall, _ = classify_interpolants(
                instance,
                stepK,
                pddef,
                reverse=reverse,
                permute=permute,
                permute_index=permute_index,
            )
            cnf_overall, _ = classify_smt_cnf(
                instance,
                stepK,
                pddef,
                reverse=reverse,
                permute=permute,
                permute_index=permute_index,
            )
            row: Dict[str, str] = {
                "instance_name": instance,
                "K": str(stepK),
                "interpolant_status": normalize_status(interp_overall),
                "smt2cnf_status": normalize_status(cnf_overall),
                "category": category_map[instance],
            }
            if scaling:
                row["local_max_k"] = str(K)
            rows.append(row)
            print(
                f"[{instance}.{stepK}] Interp={row['interpolant_status']}, "
                f"SMT2CNF={row['smt2cnf_status']} (reverse={reverse}, permute={permute}, permute_index={permute_index}, scaling={scaling})"
            )

    pddef_suffix = "" if pddef == 1 else f".pddef{pddef}"
    out_path = f"{category}{pddef_suffix}{perm_suffix}{'.scaling' if scaling else ''}{'.reverse' if reverse else ''}.csv"
    with open(out_path, "w", newline="") as f:
        fieldnames = ["instance_name", "K", "interpolant_status", "smt2cnf_status", "category"]
        if scaling:
            fieldnames = ["instance_name", "local_max_k", "K", "interpolant_status", "smt2cnf_status", "category"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out_path}")
    # exit()

    # 汇总 done 比例
    total = len(rows)
    if total > 0:
        interp_done = sum(1 for r in rows if r["interpolant_status"] == "done")
        cnf_done = sum(1 for r in rows if r["smt2cnf_status"] == "done")
        both_done = sum(1 for r in rows if r["interpolant_status"] == "done" and r["smt2cnf_status"] == "done")
        print(
            f"Interpolants done ratio: {interp_done}/{total} ({interp_done/total:.1%}); "
            f"SMT→CNF done ratio: {cnf_done}/{total} ({cnf_done/total:.1%}); "
            f"Both done: {both_done}/{total} ({both_done/total:.1%})"
        )
    return

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--instances",
        type=str,
        default=",".join(DEFAULT_TARGET_INSTANCES),
        help="逗号分隔的 instance 列表（默认使用 dumb_sceduler.sh 的 target_list）",
    )
    parser.add_argument(
        "--K_list",
        type=str,
        default=",".join(str(k) for k in DEFAULT_K_LIST),
        help="逗号分隔的 K 列表，例如 '10,20,30'",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="传给 AbsorptionExperiment 的 category（可选：exponential, linear, all 等）",
    )
    parser.add_argument(
        "--use_summary",
        type=str,
        default="regression_summary.csv",
        help="是否使用 summary 文件来判断 interpolant file和k",
    )
    parser.add_argument(
        "--output_status_to_csv",
        action="store_true",
        default=False,
        help="输出 status 汇总 CSV；若同时指定 --scaling，则输出 K=1..local_max_k-1 的长表到 *.scaling*.csv",
    )
    parser.add_argument(
        "--check_pds_ratio",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--proofgate",
        action="store_true",
        default=False,
        help="Shortcut: schedule proofgate pipeline (pddef=3) to compute def3 proofdoors",
    )
    parser.add_argument(
        "--reverse",
        dest="reverse",
        action="store_true",
        help="生成反向的 smt / interpolant（默认关闭）",
    )
    parser.add_argument(
        "--interpolation",
        action="store_true",
        default=False,
        help="是否只计算 interpolant",
    )
    parser.add_argument(
        "--force_refresh",
        action="store_true",
        default=False,
        help="强制重算：interpolation 时重算 interpolants；full pipeline 时重算 smt2cnf（覆盖已有文件）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=-1,
        help="最多调度前 N 个 instance（<=0 表示不限制）",
    )
    parser.add_argument(
        "--do_absorption",
        action="store_true",
        default=False,
        help="是否在 SMT→CNF 之后提交 absorption manage job（默认关闭）",
    )
    parser.add_argument(
        "--scaling",
        action="store_true",
        default=False,
        help="scaling analysis with proofdoor size",
    )
    parser.add_argument(
        "--completed_interpolants_only",
        action="store_true",
        default=False,
        help="use only completed interpolants",
    )
    parser.add_argument(
        "--prepare_formula",
        action="store_true",
        default=False,
        help="For each name in regression_summary (filtered by --category), submit one Slurm job: "
        "generate formula K=2..20, run CaDiCaL with proof (--plain), 32G/20h, timeout 1600s per solve; write info JSON.",
    )
    parser.add_argument(
        "--prepare_all_formula_interpolants",
        action="store_true",
        default=False,
        help="For each name in regression_summary (ALL instances; ignores --category), and for each K=2..min(local_max_k,10): "
        "check interpolants; if missing, submit Slurm jobs to compute interpolants (stage-1 only).",
    )

    parser.add_argument(
        "--no_reverse",
        dest="reverse",
        action="store_false",
        help="禁用反向 smt / interpolant",
    )
    parser.add_argument(
        "--permute",
        type=str,
        choices=SCRAMBLE_TYPES,
        default=None,
        help="Permute type for scrambled CNF",
    )
    parser.add_argument(
        "--permute_index",
        type=int,
        default=0,
        help="Permutation index (used as subfolder under scrambled_cnfs/<K>/<index>/)",
    )
    # reverse 默认关闭：只有显式传 --reverse 才开启
    parser.set_defaults(reverse=False, permute=None)

    args = parser.parse_args()
    pddef = 3 if args.proofgate else PDDEF
    if args.output_status_to_csv:
        output_status_to_csv(
            args.category,
            reverse=args.reverse,
            permute=args.permute,
            permute_index=args.permute_index,
            scaling=args.scaling,
            pddef=pddef,
        )
        return
    if args.prepare_formula:
        if not args.use_summary or not os.path.exists(args.use_summary):
            raise ValueError("--prepare_formula requires --use_summary pointing to an existing CSV (e.g. regression_summary.csv)")
        summary_df = pd.read_csv(args.use_summary)
        if "instance_name" not in summary_df.columns:
            raise ValueError("summary CSV 缺少列: instance_name")
        if args.category is not None and "best_model" in summary_df.columns:
            filtered = summary_df[summary_df["best_model"] == args.category]
        else:
            filtered = summary_df
        names = list(filtered["instance_name"].astype(str).str.strip().unique())
        names = [n for n in names if n]
        if not names:
            print("No names in regression_summary (for given --category); nothing to submit.")
            return
        submit_prepare_formula_jobs(names, use_summary=args.use_summary, category=args.category)
        return
    if args.prepare_all_formula_interpolants:
        if not args.use_summary or not os.path.exists(args.use_summary):
            raise ValueError(
                "--prepare_all_formula_interpolants requires --use_summary pointing to an existing CSV "
                "(e.g. regression_summary.csv)"
            )
        summary_df = pd.read_csv(args.use_summary)
        required_cols = {"instance_name", "local_max_k"}
        missing = required_cols - set(summary_df.columns)
        if missing:
            raise ValueError(f"summary CSV 缺少必要列: {sorted(missing)}")

        # Per user request: this option schedules for *all* instances, regardless of --category.
        filtered = summary_df
        instance_k_map = dict(zip(filtered["instance_name"], filtered["local_max_k"]))
        instance_k_map = dict(sorted(instance_k_map.items()))

        # Per requirement: K limit is fixed to 10 for now.
        prepare_all_formula_interpolants(
            instance_k_map,
            k_limit=10,
            pddef=pddef,
            reverse=args.reverse,
            permute=args.permute,
            permute_index=args.permute_index,
            force_refresh=args.force_refresh,
        )
        return
    if args.use_summary:
        summary_df = pd.read_csv(args.use_summary)

        required_cols = {"instance_name", "local_max_k", "best_model"}
        missing = required_cols - set(summary_df.columns)
        if missing:
            raise ValueError(f"summary CSV 缺少必要列: {sorted(missing)}")

        filtered = summary_df[summary_df["best_model"] == args.category]
        # filtered = summary_df[summary_df["best_model"] == "linear"]
        instance_k_map = dict(zip(filtered["instance_name"], filtered["local_max_k"]))
        instance_k_map = dict(sorted(instance_k_map.items()))
        # limit = 10
        # limit = 100
        limit = args.limit
        count  = 0
        if args.check_pds_ratio:
            check_pds_ratio(instance_k_map, pddef=pddef)
            return
        for idx, inst in enumerate(instance_k_map.keys()):
            if args.completed_interpolants_only:
                if get_smt_cnf_status(inst, instance_k_map[inst], pddef=pddef) != status.done:
                    continue

            if args.permute:
                limit = PERMUTE_LIMIT
            if limit > 0 and count >= limit:
                break
            count += 1
            K = instance_k_map[inst]
            if args.scaling:


                for stepK in range(1, K):
                    schedule_for_instance(
                        inst,
                        stepK,
                        pddef=pddef,
                        category=args.category,
                        reverse=args.reverse,
                        interpolation=args.interpolation,
                        permute=args.permute,
                        permute_index=args.permute_index,
                        do_absorption=args.do_absorption,
                        force_refresh=args.force_refresh,
                    )
                continue
            try:
                schedule_for_instance(
                    inst,
                    K,
                    pddef=pddef,
                    category=args.category,
                    reverse=args.reverse,
                    interpolation=args.interpolation,
                    permute=args.permute,
                    permute_index=args.permute_index,
                    do_absorption=args.do_absorption,
                    force_refresh=args.force_refresh,
                )
            except Exception as e:
                print(f"[{inst}.{K}] Error during scheduling: {e}")
    else:
        instances = [x for x in args.instances.split(",") if x]
        k_list = [int(x) for x in args.K_list.split(",") if x]

    # instances: List[str] = [x for x in args.instances.split(",") if x]
    # k_list: List[int] = [int(x) for x in args.K_list.split(",") if x]

    # 也可以在这里按 category 从 get_instance_list 动态选实例
    # if args.category and args.instances == "":
    #     instances = get_instance_list(args.category)
    # print(instances)
    # for inst in instances[:100]:
    #     if inst not in INSTANCE_K_MAP:
    #         print(f"[{inst}] Instance not found in INSTANCE_K_MAP")
    #         for K in k_list:
    #             try:
    #                 schedule_for_instance(inst, K, category=args.category)
    #             except Exception as e:
    #                 print(f"[{inst}.{K}] Error during scheduling: {e}")
    #     else:
    #         K = INSTANCE_K_MAP[inst]
    #         try:
    #             schedule_for_instance(inst, K, category=args.category)
    #         except Exception as e:
    #             print(f"[{inst}.{K}] Error during scheduling: {e}")


if __name__ == "__main__":
    # 确保工作目录在项目根（假设本文件位于 scripts/ 下）
    os.chdir(Path(__file__).resolve().parent.parent)
    main()