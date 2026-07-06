# Reproduction Guide (Slurm/HPC)

This guide assumes [SMOKETEST.md](SMOKETEST.md) passes and a Slurm cluster is
available. Commands with `--manage` submit Slurm jobs. Note that, due to hpc policy difference, the slurm commands might not necessarily work in all clusters. Some editing is need should that happen.

A full reproduction takes days to weeks.

This document is tested on compute canada rorqual/fir/narval hpc

## Section IV: BMC Scalability Study

Activate the BMCBenchmark environment first:

```bash
cd BMCBenchmark
source .env
source $PYENVPATH_BMC
```
The subsections assume we are in ./BMCBenchmark/

### Full-scale (1 day)

Generate formulas and solve (Slurm, 1day):

```bash
python src/scripts/prepare_formulas.py --k_limit 100 --manage
```

Collect solving times (Slurm, fast):

```bash
python src/scripts/Experiments/collect_solving_time.py --all_slurm
```

Fit regression models and label families (local, fast):

```bash
python src/scripts/Experiments/direct_regression_analysis.py
```

Outputs: `regression_summary.csv` and `figures/scalability/`.


### Run the same BMC pipeline on the reduced AIG set.
python src/scripts/prepare_formulas.py --k_limit 100 --manage
python src/scripts/Experiments/collect_solving_time.py --all_slurm
python src/scripts/Experiments/direct_regression_analysis.py
```

### (Optional) Select K upper bounds for proofdoor computation
A instance-K-map has already been provided in the main folder, this is optional

```bash
python find_local_max_k.py --summary regression_summary.json
cp regression_summary_k.json ../regression_summary.json
```

The goal is to use small but representative K here. K selection rules: linear families always use K=10; polynomial families are
skipped (-1); exponential families use the smallest K ≥ 5 at a local
solving-time maximum (many exponential families oscillate between even/odd K (as reported in paper Appendix) and we found that, for the linear datapoints in exponential family, their proofdoor size is also small. Therefore the local max K are of higher probability to be unfolding depths belonging to exponential trend).

## Section V-B: Proofdoor Computation

### Strongest proofdoors (BVESPC)
Cluster manager per category:

```bash
python scripts/strongest_pd/manage_spd_computation.py --K 10 --category linear
python scripts/strongest_pd/manage_spd_computation.py --K 10 --category exponential

# weakest proofdoors are computed by spd pipeline reversely and then converted to forward wpd (named mpd in the code)
python scripts/strongest_pd/manage_spd_computation.py --K 5 --category exponential --reverse 
```

Outputs under `ProofDoorBenchmark/` (paths managed by `scripts/utils/paths.py`).

(Optional) The number of successfully computed strongest proofdoors is computed by

```bash
python scripts/strongest_pd/stat_spd.py \
  --K 5 \
  --K_max 10 \
  --category linear \     
  --output spd_stats_linear_k5_to_10.csv
python scripts/strongest_pd/stat_spd.py \
  --K 5 \
  --K_max 10 \
  --category exponential \     
  --output spd_stats_exponential_k5_to_10.csv
```

Note: pddef number represents different proofdoor type/computation methods, in the paper we used iz3 proofdoors (pddef=1), strongest proofdoors (pddef=5) and weakest proofdoors(pddef=7). 

### McMillan interpolants (IPCCP, iZ3)

```bash
# interpolation jobs
python scripts/pipeline_scheduler.py --use_summary regression_summary.csv \
  --category linear --interpolation
# after jobs finish: SMT-to-CNF conversion
python scripts/pipeline_scheduler.py --use_summary regression_summary.csv \
  --category linear
# status CSV
python scripts/pipeline_scheduler.py --use_summary regression_summary.csv \
  --category linear --output_status_to_csv
```

Same with `--category exponential` (paper used data from `--scaling ` for computing with a variaty of K, which takes weeks).

Outputs: `ProofDoorBenchmark/interpolants/`, `ProofDoorBenchmark/interpolant_as_cnfs_*/`,
`*.csv`, `SlurmLogs/`.

Note: the number of successfully computed iz3 proofdoors is given by exponential.scaling.csv and linear.scaling.csv

Note: `scripts/spd_cadet/` contains the exploratory Manthan/BFSS pipeline
mentioned in the paper; it is not needed for the main claims.

## Section V-C RQ1: Incremental Absorption (linear)


### iZ3 proofdoors
First normalize the proofdoor computation data to input format of absorption experiments
``` bash
python scripts/build_proofdoor_computation_summary.py   --summary regression_summary.csv --output proofdoor_computation_summary_linear.csv   --category linear   --pddef 1
python scripts/build_proofdoor_computation_summary.py   --summary regression_summary.csv --output proofdoor_computation_summary_exponential.csv   --category exponential   --pddef 1
```
Then start the absorption experiment

```bash
python scripts/AbsorptionExperiment.py   --from_summary proofdoor_computation_summary_linear.csv   --category linear
python scripts/AbsorptionExperiment.py   --from_summary proofdoor_computation_summary_exponential.csv   --category exponential
```

Absorption experiment detailed caches are in ProofDoorBenchmark/absorption_experiments/<K>
Absorption experiment figures are in figures/absorption_experiments/

### Strongest proofdoors
First normalize the proofdoor computation data to input format of absorption experiments
``` bash
python scripts/build_proofdoor_computation_summary.py   --summary regression_summary.csv --output proofdoor_computation_summary_linear_spd.csv   --category linear   --pddef 5
python scripts/build_proofdoor_computation_summary.py   --summary regression_summary.csv --output proofdoor_computation_summary_exponential_spd.csv   --category exponential   --pddef 5
```
Then start the absorption experiment

```bash
python scripts/AbsorptionExperiment.py   --from_summary proofdoor_computation_summary_linear_spd.csv   --category linear 
python scripts/AbsorptionExperiment.py   --from_summary proofdoor_computation_summary_exponential_spd.csv   --category exponential 
```

## Section V-C RQ2: Linear vs. Exponential Proofdoor Size Scaling

Same pipelines with above but with all K from 5 to 10. 
Figure is drawn by

```bash
python scripts/strongest_pd/stat_spd.py --K 5 --K_max 10  --plot
# python scripts/strongest_pd/stat_spd.py --K 5 --K_max 10  --plot --extendx2 #with scatter line estimating interpolant sizes of first timeout indexes
```

## Section V-C RQ3: Scrambling

First generate the permuted formulas and run, permute_n is the number of samples. (Fast)
```bash
python scripts/formula_permutation.py   --category linear   --permute_type clause_and_iteration   --permute_n 1   --only_success_instance   --generate  # permute iterations and order of clauses within them
python scripts/formula_permutation.py   --category linear   --permute_type clause   --permute_n 1   --only_success_instance   --generate # permute the order of all clauses
python scripts/formula_permutation.py   --category linear   --permute_type clause_and_iteration   --permute_n 1   --only_success_instance   --run # permute iterations and order of clauses within them
python scripts/formula_permutation.py   --category linear   --permute_type clause   --permute_n 1   --only_success_instance   --run # permute the order of all clauses
```

The formulas will be at
ProofDoorBenchmark/scrambled_cnfs/<K>/<permute_index>/<instance>.<K>.<permute_type>.cnf

After solving complete, to see the results (Fast): 

```bash
python scripts/formula_permutation.py   --category linear   --permute_type clause_and_iteration   --permute_n 1   --only_success_instance   --compare # permute iterations and order of clauses within them
python scripts/formula_permutation.py   --category linear   --permute_type clause   --permute_n 1   --only_success_instance   --compare # permute the order of all clauses
```
