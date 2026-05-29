# ProofDoorTools

This repository contains the scripts and derived artifacts for the experiments in
the paper *Understanding CDCL Solvers via Scalability Studies and Proofdoors*.

The code is intentionally kept close to the version used for the paper. During
review, we avoid refactoring experiment scripts so that command lines, output
paths, and cached artifacts remain stable.

## Scope

The paper has two main experimental parts, and this README follows that order.

1. Section IV: BMC scalability study over HWMCC families.
2. Section V: explanation of the linear/exponential split, including previously
   proposed parameters, proofdoor computation, absorption, and scrambling.

Several full runs were performed on a Slurm cluster. The commands below are the
entry points used for those runs; for local inspection, the repository also
contains cached CSV/JSON summaries and figures.

## Environment Setup

Use Python 3.10 or newer.

```bash
virtualenv ./env/
source ./env/bin/activate
pip install -r requirements.txt
source .env
```

The `.env` file adds `./scripts` to `PYTHONPATH`. Source it from the repository
root before running the scripts below.

This repository assumes the experiment binaries and benchmark artifacts are
already available at the paths used by the scripts. The README does not cover
building external solvers or tools.

## Repository Layout

```text
.
|-- BMCBenchmark/                 # BMC scalability pipeline checkout/artifacts
|-- ProofDoorBenchmark/           # CNFs, SMT files, interpolants, proofs, wires
|-- ProofSizeMap/                 # cached interpolant/proofdoor size data
|-- Experiments/                  # experiment-specific logs and summaries
|-- figures/                      # generated figures used for inspection/paper
|-- result/                       # dashboard-style CSV summaries
|-- scripts/                      # main experiment and analysis scripts
|-- External/                     # external tools expected by some scripts
|-- solvers/                      # solver binaries expected by some scripts
|-- regression_summary.csv        # family labels from the scalability study
`-- requirements.txt              # Python package dependencies
```

Important cached summary files:

```text
regression_summary.csv          # instance_name,best_model,local_max_k
linear.csv                      # linear-family subset
exponential.csv                 # exponential-family subset
dashboard_data.csv              # aggregated experiment dashboard data
result/pds_dashboard_linear.csv # proofdoor-size dashboard for linear families
result/pds_dashboard_merged.csv # merged proofdoor-size dashboard
```

## Section IV: BMC Scalability Study

The scalability study generates CNFs for unfolding depths `K = 1..100`, solves
each formula with CaDiCaL configured to reflect pure CDCL, records solving time
and formula size, then fits linear, polynomial, and exponential models. The
resulting family labels are stored in `regression_summary.csv`.

Generate formulas:

```bash
cd BMCBenchmark
source .env 
source $PYENVPATH
python src/scripts/prepare_formulas.py --k_limit 100 --manage
```

Collect solving-time data:

```bash
python src/scripts/collect_solving_time.py
```

Classify each family by its best scaling model:

```bash
python src/scripts/direct_regression_analysis.py
```

Expected outputs:

```text
regression_summary.csv
linear.csv
exponential.csv
figures/scalability/
```

The paper reports 333 linear, 268 polynomial, 148 exponential, and 17 unknown
families. These labels are statistical fits over the explored depth range, not
formal asymptotic complexity claims.

## Section V-A: Previously Proposed Parameters

Section V-A checks whether previously proposed formula parameters separate the
linear and exponential families. The experiments focus on clause-variable ratio,
pathwidth/treewidth-style structure, and community modularity.

Compute community modularity for CNFs:

```bash
python scripts/compute_cnf_modularity.py --K 10 --category linear --manage
python scripts/compute_cnf_modularity.py --K 10 --category exponential --manage
python scripts/compute_cnf_modularity.py --K 10 --collect --category all
```

Expected outputs:

```text
ProofDoorBenchmark/cnf_modularity/<K>/*.modularity.json
figures/cnf_modularity_K<K>.png
```

Compute pathwidth upper-bound summaries:

```bash
python scripts/compute_pathwidth.py --K 10 --instances <comma-separated-instances> --manage --plot
```

Expected outputs:

```text
temp/pathwidth/
results/pathwidth_summary_*.json
figures/pathwidth_*.png
```

The paper conclusion for these parameters is negative: they do not discriminate
the linear and exponential endpoints of the BMC scaling spectrum.

## Section V-B: Proofdoor Computation

The paper computes proofdoors by aligning proofdoor chunks with BMC unrolling
steps. Two main pipelines are used.

### Strongest Proofdoors by BVE

`scripts/strongest_pd/compute_spd.py` computes one strongest-proofdoor
interpolant for a fixed instance, depth, and cut index by encoding projection as
QDIMACS and applying bounded variable elimination plus forced elimination.

Single cut:

```bash
python scripts/strongest_pd/compute_spd.py --name <instance> --K <K> --i <index>
```

Reverse direction:

```bash
python scripts/strongest_pd/compute_spd.py --name <instance> --K <K> --i <index> --reverse
```

Cluster manager for a family/category:

```bash
python scripts/strongest_pd/manage_spd_computation.py --K <K> --category linear
python scripts/strongest_pd/manage_spd_computation.py --K <K> --category exponential
```

Expected outputs are stored under the proofdoor/interpolant directories managed
by `scripts/utils/paths.py`, primarily below `ProofDoorBenchmark/`.

### McMillan Interpolants by iZ3

`scripts/pipeline_scheduler.py` manages the iZ3 interpolation pipeline:
interpolant computation, SMT-to-CNF conversion, optional status reporting, and
optional absorption scheduling.

Schedule interpolation/CNF conversion for selected instances:

```bash
python scripts/pipeline_scheduler.py \
  --instances <comma-separated-instances> \
  --K_list 10,20,30 \
  --category linear
```

Use the scalability summary to drive a category run:

```bash
python scripts/pipeline_scheduler.py \
  --use_summary regression_summary.csv \
  --category linear \
  --K_list 10
```

Write a pipeline status CSV:

```bash
python scripts/pipeline_scheduler.py \
  --use_summary regression_summary.csv \
  --category linear \
  --K_list 10 \
  --output_status_to_csv
```

Expected outputs:

```text
ProofDoorBenchmark/interpolants/
ProofDoorBenchmark/interpolant_as_cnfs_*/
*.scaling.csv
SlurmLogs/
```

The `scripts/spd_cadet/` directory contains the Manthan/BFSS-based exploratory
pipeline mentioned in the paper. It was less efficient than the BVE pipeline in
our experiments, but the scripts are kept for reproducibility.

## Section V-C RQ1: Incremental Absorption on Linear Families

Absorption experiments test whether proofdoor clauses are absorbed by partial
CDCL proofs in the order predicted by the BMC decomposition. This is the main
experiment behind the linear-family heatmap in the paper.

Run absorption for one instance:

```bash
python scripts/AbsorptionExperiment.py \
  --K 10 \
  --main \
  --force_instance <instance> \
  --category linear \
  --use_strongest_interpolant
```

Run absorption using default McMillan-interpolant CNFs:

```bash
python scripts/AbsorptionExperiment.py \
  --K 10 \
  --main \
  --force_instance <instance> \
  --category linear
```

Draw heatmaps from existing absorption results:

```bash
python scripts/AbsorptionExperiment.py --K 10 --draw --force_instance <instance>
```

Expected outputs:

```text
Dashboard/AbsorptionExperiment_results_<K>.json
figures/absorption_experiments/<K>/
SlurmLogs/
```

A near upper-triangular heatmap indicates incremental absorption: interpolant
clauses become absorbed as the corresponding partial proof grows.

## Section V-C RQ2: Linear vs. Exponential Proofdoors

For exponential families, the same pipeline is run over instances labeled
`exponential` in `regression_summary.csv`. The paper compares sampled points in
the interpolant lattice: strongest, weakest, and McMillan interpolants.

Schedule proofdoor computation for exponential instances:

```bash
python scripts/pipeline_scheduler.py \
  --use_summary regression_summary.csv \
  --category exponential \
  --K_list 5,10 \
  --output_status_to_csv
```

Run absorption checks on exponential instances:

```bash
python scripts/AbsorptionExperiment.py \
  --K 10 \
  --main \
  --force_instance <instance> \
  --category exponential
```

Expected outputs are the same as RQ1, with files grouped by `K`, instance, and
interpolant definition. The key paper-level observation is that the sampled
proofdoors for exponential families grow large and usually do not show the
incremental absorption pattern seen for linear families.

## Section V-C RQ3: Scrambling Linear Instances

The scrambling experiment perturbs linear BMC formulas while preserving the
clause set and satisfiability. The two main modes are by iteration and by
clause. In the scripts these are controlled by `--permute`.

Schedule scrambled interpolation:

```bash
python scripts/pipeline_scheduler.py \
  --use_summary regression_summary.csv \
  --category linear \
  --K_list 10 \
  --permute iteration \
  --permute_index 0
```

Run absorption on scrambled instances:

```bash
python scripts/AbsorptionExperiment.py \
  --K 10 \
  --main \
  --force_instance <instance> \
  --category linear \
  --permute iteration \
  --permute_index 0
```

For clause-level scrambling, replace `--permute iteration` with
`--permute clause`.

Expected outputs use suffixes such as:

```text
.perm_iteration_0
.perm_clause_0
```

The paper-level observation is that scrambling linear instances increases
solving time and McMillan proofdoor size, while successful McMillan runs still
show absorption of the produced interpolants.

## Inspecting Cached Results

The following commands are useful when checking already generated artifacts.

Summarize proofdoor-size data:

```bash
python ProofSizeMap/combine_json.py
python ProofSizeMap/check_interpolant_finish_percentage.py
```

Analyze proofdoor-size scaling:

```bash
python scripts/PDSScalingExperiment.py --category linear --pddef 1
python scripts/PDSScalingExperiment.py --category exponential --pddef 1
```

Inspect or regenerate proofdoor/solving-time plots:

```bash
python scripts/process_interpolants.py --ComparePDS --FormulaCategory linear --K 10
python scripts/process_interpolants.py --CheckPDCSolvingTimeCorrelation --FormulaCategory linear --K 10
```

Common output locations:

```text
ProofSizeMap/data/
Experiments/pds_scaling/result/
result/
figures/
```

## Reviewer Notes

Many commands with `--manage` submit Slurm jobs and are intended for the cluster
environment used for the paper. Single-instance commands without `--manage` are
better for local sanity checks.

The `BMCBenchmark/` directory is the entry point for Section IV's scalability
pipeline. In this checkout it may contain only artifacts or be populated by a
separate benchmark checkout, depending on how the review artifact is packaged.

The scripts use cached data aggressively. Before forcing recomputation, inspect
the existing CSV/JSON files and figure directories listed above.

The paper uses absorption as a proxy for whether CDCL has derived clauses with
the same unit-propagation effect as the proofdoor interpolants; the scripts do
not require the solver to learn the exact same clauses syntactically.
