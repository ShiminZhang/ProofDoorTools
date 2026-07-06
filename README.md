# ProofDoorTools

This repository contains the scripts for the experiments in
the paper *Understanding CDCL Solvers via Scalability Studies and Proofdoors*.

The code is intentionally kept close to the version used for the paper. During
review, we avoid refactoring experiment before publish for stability.

## Documentation Map

| Document | Purpose |
|----------|---------|
| [SMOKETEST.md](SMOKETEST.md) | Local sanity check, no Slurm required, < 1 hour. |
| [REPRODUCE.md](REPRODUCE.md) | Full reproduction instructions (Slurm required). |

## Environment Setup

We used Python 3.11.

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

## Submodules

```bash
git submodule init
git submodule update
```

## Setup dependencies
```bash
./build_dependencies.sh
```

## Reviewer Notes

Commands with `--manage` submit Slurm jobs and are intended for the cluster
environment used for the paper. Single-instance commands without `--manage`
run locally; SMOKETEST.md collects the local path.

The scripts use cached data aggressively.

Absorption checker is a joint functionality provided by External/minisat_absorption_checker/ and scripts/AbsorptionExperiment.py
