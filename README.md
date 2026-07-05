# ProofDoorTools

This repository contains the scripts and derived artifacts for the experiments in
the paper *Understanding CDCL Solvers via Scalability Studies and Proofdoors*.

The code is intentionally kept close to the version used for the paper. During
review, we avoid refactoring experiment scripts so that command lines, output
paths, and cached artifacts remain stable.

## Documentation Map

| Document | Purpose |
|----------|---------|
| [SMOKETEST.md](SMOKETEST.md) | Local sanity check, no Slurm required, < 1 hour. Start here. |
| [REPRODUCE.md](REPRODUCE.md) | Full reproduction instructions (Slurm/HPC), with a small-scale and a full-scale tier. |
| [CLAIMS.md](CLAIMS.md) | Mapping from each paper claim/number to the command that reproduces it and the file that contains it. |

## Scope

The paper has two main experimental parts:

1. Section IV: BMC scalability study over HWMCC families.
2. Section V: explanation of the linear/exponential split, including previously
   proposed parameters, proofdoor computation, absorption, and scrambling.

Full runs were performed on a Slurm cluster. The repository also contains
cached CSV/JSON summaries and figures so that most results can be inspected
without recomputation.

## Environment Setup

We used Python 3.10.

```bash
virtualenv ./env/
source ./env/bin/activate
pip install -r requirements.txt
source .env
```

The `.env` file adds `./scripts` to `PYTHONPATH`. Source it from the repository
root before running any scripts.

Note on Z3: the interpolation experiments use a separately built iZ3-capable Z3
binary (`./bin/z3`); the `z3-solver` pip package is a different artifact used only
by helper scripts. See REPRODUCE.md §Prerequisites.
<!-- TODO: confirm iZ3 z3 version and how it is obtained/built -->

## Submodules

```bash
git submodule init
git submodule update
```

## Repository Layout

```text
.
|-- BMCBenchmark/                 # Section IV scalability pipeline (submodule)
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
linear.csv / exponential.csv    # per-category subsets
dashboard_data.csv              # aggregated experiment dashboard data
linear.scaling.csv              # per-(instance,K) IPCCP pipeline status, linear
exponential.scaling.csv         # per-(instance,K) IPCCP pipeline status, exponential
result/pds_dashboard_*.csv      # proofdoor-size dashboards
```

## Reviewer Notes

Commands with `--manage` submit Slurm jobs and are intended for the cluster
environment used for the paper. Single-instance commands without `--manage`
run locally; SMOKETEST.md collects the local path.

The scripts use cached data aggressively. Before forcing recomputation, inspect
the existing CSV/JSON files and figure directories listed above.

The paper uses absorption as a proxy for whether CDCL has derived clauses with
the same unit-propagation effect as the proofdoor interpolants; the scripts do
not require the solver to learn the exact same clauses syntactically.
