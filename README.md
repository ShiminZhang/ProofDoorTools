To ensure all scripts remain correct when paper is under review, this repo will not be refactored until paper publication.

# BMC scalability analysis
## add scripts to pythonpath
```
source .env
```

## Generate all CNF formulas

```
cd BMCBenchmark
python src/scripts/prepare_formulas.py --k_limit 100 --manage
```

## collect generated data
```
python src/scripts/collect_solving_time.py
```

## categorization
```
python src/scripts/direct_regression_analysis.py
```
All the results can be seen in figures/


# Explanation via Proofdoor

## add scripts to pythonpath
```
source .env
```

## Proofdoor Computation(BVE)
See scripts/strongest_pd/compute_spd.py

Manthan/BFSS based see scripts/spd_cadet/

## Proofdoor Computation(iZ3)
See scripts/pipeline_scheduler.py

## Absorption checking
See scripts/AbsorptionExperiment.py 
