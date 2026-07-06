# 累积分割法 (Cumulative Partition) - SPD Manthan 计算指南

## 概述

你已经有三个新的脚本用于使用**累积分割法**计算 Craig interpolants：

1. **compute_spd_skolem_cumulative.py** — 计算 Skolem 函数
2. **run_spd_manthan_step_cumulative.py** — SLURM 任务执行器
3. **manage_spd_manthan_computation_cumulative.py** — 批量提交脚本

## 核心差异

### 原始方法 (现有代码)
对于第 i 个迭代：
```
左部分:  I_{i-1} ∧ A_i         (前面的 interpolant + 当前迭代)
右部分:  A_{i+1} ∧ ... ∧ A_K   (剩余所有迭代)
```
- 需要保存 I_{i-1}（前面计算的 interpolant CNF）
- 形成依赖链：第 i+1 步依赖第 i 步
- 前面步的错误会阻止后续步

### 累积分割法 (新方法)
对于第 i 个迭代：
```
左部分:  A_0 ∧ A_1 ∧ ... ∧ A_i     (所有前 i+1 个迭代)
右部分:  A_{i+1} ∧ ... ∧ A_K       (剩余迭代)
```
- **不依赖 I_{i-1}**，每次都从原始 CNF 独立分割
- **所有迭代相互独立**
- 可以：
  - 完全并行运行所有迭代（--parallel-all）
  - 选择性地重新计算某些迭代
  - 跳过已完成的迭代

## 输出目录

运行累积分割法会在以下目录生成输出：

```
ProofDoorBenchmark/
├── skolem_spd_manthan_cumulative/{K}/          # Manthan Skolem 函数
├── interpolant_aig_manthan_cumulative/{K}/     # ABC 生成的 AAG
└── interp_cnf_spd_manthan_cumulative/{K}/      # 验证后的 interpolant CNF
```

原始方法的输出在相同目录但不含 `_cumulative` 标记。

## 使用方法

### 1. 单个实例，完整链（带依赖）

```bash
python manage_spd_manthan_computation_cumulative.py --name cal4 --K 7
```

这会为 `cal4` 创建 K=7 个任务 (i=0 到 6)，形成一个依赖链。

### 2. 单个实例，完全并行

```bash
python manage_spd_manthan_computation_cumulative.py --name cal4 --K 7 --parallel-all
```

所有 7 个迭代同时提交，没有依赖关系。更快，但需要更多资源。

### 3. 单个迭代

```bash
python manage_spd_manthan_computation_cumulative.py --name cal4 --K 7 --i 2
```

只计算第 i=2 个迭代。

### 4. 批量处理一个类别中的所有实例

```bash
python manage_spd_manthan_computation_cumulative.py --K 7 --category linear --parallel-all
```

对所有 'linear' 类别的实例，并行运行它们的所有迭代。

### 5. 继续已完成的任务

```bash
python manage_spd_manthan_computation_cumulative.py --K 7 --category linear --start-after 2
```

只运行 i >= 3 的实例，跳过那些 i=2 尚未完成的。

### 6. 强制重新运行（覆盖已有输出）

```bash
python manage_spd_manthan_computation_cumulative.py --name cal4 --K 7 --force
```

删除所有现有输出并重新计算。

### 7. 自定义资源

```bash
python manage_spd_manthan_computation_cumulative.py --name cal4 --K 7 --mem 40g --time 4:00:00
```

每个任务分配 40GB 内存和 4 小时墙时间。

## 代码架构

### compute_spd_skolem_cumulative.py

关键函数：
```python
compute_spd_skolem_cumulative(name, K, i, backend, export_qdimacs_only=False)
```

- 从原始 CNF 读取并按迭代分割
- 构造 QDIMACS：`∀(shared_vars) ∃(elim_vars) (A_0...A_i ∧ A_{i+1}...A_K)`
  - `shared_vars` = 两部分都有的变量（通用量词）
  - `elim_vars` = 仅左部分有的变量（存在量词）
- 调用 Manthan 生成 Skolem 函数
- 返回 Skolem 文件路径

### run_spd_manthan_step_cumulative.py

执行三步流程：
1. **compute_spd_skolem_cumulative** — 生成 Skolem 函数
2. **skolem_to_aig** — 将 Skolem 替换到 AAG（通过 ABC）
3. **verify_skolem_interpolant** — 验证 interpolant 条件并保存 CNF

使用了包装函数 `_skolem_to_aig_cumulative()` 和 `_verify_interpolant_cumulative()` 
来自动将路径从 `_cumulative` 目录重定向。

### manage_spd_manthan_computation_cumulative.py

SLURM 提交脚本：
- `submit_iter()` — 提交单个迭代
- `submit_all_iters()` — 提交所有迭代，可选择依赖链或并行
- `main()` — 解析 CLI 参数并处理类别过滤

## 工作流示例

```bash
# 为 linear 类别的所有实例计算 K=10 的 interpolants，使用累积分割
python manage_spd_manthan_computation_cumulative.py \
    --K 10 \
    --category linear \
    --parallel-all \
    --mem 30g \
    --time 3:00:00

# 检查一个实例的结果
ls ProofDoorBenchmark/interp_cnf_spd_manthan_cumulative/10/instance_name.10.*.cnf

# 如果某个迭代失败，重新运行它（仅那个迭代）
python manage_spd_manthan_computation_cumulative.py \
    --name instance_name \
    --K 10 \
    --i 3 \
    --force
```

## 关键优势

1. **完全独立** — 每个迭代独立计算，可以并行化或选择性重新运行
2. **简化逻辑** — 无需保存和加载前面的 interpolants
3. **灵活重新计算** — 可以轻松对单个 K 或实例重新计算
4. **可扩展** — 支持大规模批处理，带有细粒度控制

## 调试

### 查看单个任务的 QDIMACS

```python
from spd_cadet.compute_spd_skolem_cumulative import compute_spd_skolem_cumulative
compute_spd_skolem_cumulative("instance_name", K=7, i=2, backend='manthan', export_qdimacs_only=True)
```

输出路径：`./ProofDoorBenchmark/progressive_qdimacs_spd_skolem_cumulative/{K}/...`

### 检查 Manthan 输出

查看 SLURM 日志：
```bash
tail -f SlurmLogs/compute_spd_manthan_cumulative/k_10/instance_name.10.*.log
```

### 验证 interpolant 属性

运行脚本时会打印验证信息：
- `[VAR]` — 检查 interpolant 变量包含在共享变量中
- `[LEFT]` — 检查 `I_{i-1} ∧ A ⊨ I`（左蕴含 interpolant）
- `[RIGHT]` — 检查 `I ∧ B` 无满足模型（interpolant 与右部分不相容）

## 注意事项

1. **Manthan 依赖** — 确保 `./External/manthan` 存在且已正确配置
2. **ABC 工具** — 需要 ABC 来转换 AAG（检查配置）
3. **CaDiCaL** — 用于验证，位置应为 `./solvers/cadical`
4. **资源** — Manthan 计算量大，分配足够内存（默认 20GB 通常足够）
