# Smoke Test (local, no Slurm, < 1 hour)

Goal: verify on a single machine that the toolchain works end to end, using one
small linear instance and one small exponential instance. This does NOT
reproduce the paper's numbers — see [REPRODUCE.md](REPRODUCE.md) for that.

This document is tested on compute canada rorqual/fir/narval hpc

## Prerequisites

- Linux x86-64 (binaries in `solvers/` and repo root are built for this).
- Python 3.10 environment set up as in [README.md](README.md).
- Environment activated:

```bash
source ./env/bin/activate
source .env
```

## Test Instances

| Category | Instance | K | Why chosen |
|----------|----------|---|------------|
| linear | `139442p0` | 2 | small |
| exponential | `beemprdcell2f1` | 3 | small, note that this is only to test the pipeline. Higher K might be needed to reproduce. |

## Step 1: Generate CNF (Section IV pipeline) and solve

```bash
cd BMCBenchmark
source .env
source $PYENVPATH_BMC
python src/scripts/prepare_formulas.py --name 139442p0 --k_limit 2 --time_limit 1600
```

Expected output: `./BMCBenchmark/data/cnfs/139442p0/`

## Step 2: Regression

```bash
python src/scripts/Experiments/direct_regression_analysis.py --instance 139442p0 --summary "" --output results/139442p0_regression.json

grep 139442p0 regression_summary.csv   # linear
```
plot will be at: ./results/plots/139442p0_regression_analysis.png
result: results/139442p0_regression.json

## Step 3: proofdoor computation


```bash
# Option A iz3 proofdoors (McMillan proofdoors) — manage scripts use pddef=1
python scripts/prepare_single.py --name 139442p0 --K 10 --index 0 --pddef 1 --pre_interpolant
python scripts/prepare_single.py --name 139442p0 --K 10 --index 0 --pddef 1 --interpolant_only

# Option B strongest proofdoors (BVE)
python scripts/strongest_pd/compute_spd.py --name 139442p0 --K 10 --i 0            # strongest, for weakest please see REPRODUCE.md

```
result: `ProofDoorBenchmark/interpolants_def1/10/139442p0.10.0.interpolant` (Option A) or `ProofDoorBenchmark/interpolants_def5/10/139442p0.10.0.interpolant` (Option B)

Note: pddef number represents different proofdoor type/computation methods, in the paper we used iz3 proofdoors (pddef=1), strongest proofdoors (pddef=5) and weakest proofdoors(pddef=7). 

## Step 5: Absorption check + heatmap
note that the --index/--i above has to cover 0~9 before the following heatmap being meaningful
```bash
python scripts/AbsorptionExperiment.py \
  --instance 139442p0 \
  --K 10 \
  --category linear
  --pddef 1
```

results: `figures/absorption_experiments/10/pddef_1/Literal Absorption Pass Percentage Heatmap 139442p0 (CaDiCaL)_withFormula_notrimmed_forward.png`
