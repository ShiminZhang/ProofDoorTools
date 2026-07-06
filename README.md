# ProofDoorTools

This repository contains the scripts for the experiments in
the paper *Understanding CDCL Solvers via Scalability Studies and Proofdoors*.

The code is intentionally kept close to the version used for the paper. During
review, we avoid refactoring experiment before paper publishing for stability.

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
root before running any scripts. The BMCBenchmark repo uses another .env.

Note on Z3: the interpolation experiments use a separately built Z3-4.7.1
binary (`./bin/z3`); the `z3-solver` pip package is a different artifact used only
by helper scripts. In case the included distribution cannot build, please download a suitable Z3-4.7.1 from their repo and put in External/.

## Submodules

```bash
git submodule init
git submodule update
```

## Setup dependencies and prepare the binaries
```bash
./build_dependencies.sh
```

## Reviewer Notes

For implementation details: Absorption checking is a joint functionality provided by External/minisat_absorption_checker/ and scripts/AbsorptionExperiment.py. BVE based proofdoor computation has part of implementation in External/kissat_bve. The other implementations are in scripts/.

For data: Paper related data & logs & figures are in PaperData/

The scripts use cached data aggressively and generates tens of thousands of files. It may take TBs of disk storage. One way to save storage is to delete BMCBenchmark/data/cnfs after the BMCScaling study is done.
