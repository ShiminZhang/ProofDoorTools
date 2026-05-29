#!/bin/bash                                                    
#SBATCH --time=0-12:0:0                                                      
#SBATCH --account=def-vganesh 
#SBATCH --mem=10G
#SBATCH --cpus-per-task=1
#SBATCH --output=./dumb_runner_%j.log

section=$1
# git add -A; git commit -m "update"; git push
# sleep 2h
source .env
source $PYENVPATH

if [ "$section" == "1" ]; then
    module load apptainer/1.4.5
    apptainer exec --bind $PWD:/work sage.sif   sage -python /work/scripts/compute_pathwidth_sage.py /work/ProofDoorBenchmark/cnfs/10/139442p0.10.cnf --mode block
    # python scripts/pipeline_scheduler.py --no_reverse  --category linear
    # python scripts/pipeline_scheduler.py --no_reverse  --category exponential
    # python scripts/pipeline_scheduler.py --reverse  --category linear --interpolation
    # python scripts/pipeline_scheduler.py  --category linear --interpolation --scaling
    # python scripts/pipeline_scheduler.py --reverse  --category exponential --interpolation
    # python scripts/prepare.py --focus_name $2 --prepare_sequential --K $3
    # python scripts/AbsorptionExperiment.py --test
    #  python scripts/SMTTranslationToCNFExperiment.py --main --K 10 --category linear --time "8:00:00"
fi

if [ "$section" == "2" ]; then
    python scripts/prepare.py   --compute_strongest_interpolant   --from_regression_summary   --regression_summary_path regression_summary.csv   --category exponential --K 6
    python scripts/prepare.py   --compute_strongest_interpolant   --from_regression_summary   --regression_summary_path regression_summary.csv   --category linear --K 6
    # python scripts/compute_pathwidth.py --manage --K 9 --mode block
    # python scripts/compute_pathwidth.py --manage --K 8 --mode block
    # python scripts/compute_pathwidth.py --manage --K 7 --mode block
    # python scripts/compute_pathwidth.py --manage --K 6 --mode block
    # python scripts/compute_pathwidth.py --manage --K 5 --mode block
    # python scripts/compute_pathwidth.py --manage --K 4 --mode block
    # python scripts/compute_pathwidth.py --manage --K 3 --mode block
    # python scripts/compute_pathwidth.py --manage --K 2 --mode block
    # python scripts/compute_pathwidth.py --manage --K 1 --mode block
    # python scripts/compute_pathwidth.py --cnf ProofDoorBenchmark/cnfs/10/139442p0.10.cnf
    # python scripts/AbsorptionExperiment.py --from_summary exponential.reverse.csv --reverse
    # python scripts/AbsorptionExperiment.py --from_summary linear.reverse.csv --reverse
    # python scripts/AbsorptionExperiment.py --from_summary exponential.reverse.csv --reverse --use_glucose_proof
    # python scripts/AbsorptionExperiment.py --from_summary linear.reverse.csv --reverse --use_glucose_proof
    # python scripts/AbsorptionExperiment.py --from_summary exponential.csv
    # python scripts/AbsorptionExperiment.py --from_summary linear.csv
    # python scripts/AbsorptionExperiment.py --from_summary exponential.csv --use_glucose_proof
    # python scripts/AbsorptionExperiment.py --from_summary linear.csv  --use_glucose_proof
    # python scripts/prepare.py --prepare_sequential --pddef 1 --manage --K 10 --category exponential,linear
    # python ./scripts/prepare_single.py --name 6s399rb22 --K 100 --pre_interpolant --pddef 1 --force_refresh
    # python scripts/SMTTranslationToCNFExperiment.py --K 100 --main --instance 6s399rb22
    # python scripts/sanity_check.py --K 5 --pddef 3 --all > sanity_check_def3_5.log
    # python scripts/sanity_check.py --K 15 --pddef 3 --all > sanity_check_def3_15.log
fi

if [ "$section" == "3" ]; then
    
    # python scripts/prepare.py --compute_strongest_interpolant --from_regression_summary --category linear --focus_name 139442p0
    # python scripts/prepare.py --compute_strongest_interpolant --from_regression_summary --category linear --focus_name 139442p1
    # python scripts/prepare.py --compute_strongest_interpolant --from_regression_summary --category linear
    python scripts/pipeline_scheduler.py  --category exponential --scaling --interpolation --completed_interpolants_only
    python scripts/StrongestInterpolantToCNF.py --instance nusmvsyncarb5p2 --K 10 --manage
    python scripts/StrongestInterpolantToCNF.py --instance power2bit8 --K 10 --manage
    python scripts/StrongestInterpolantToCNF.py --instance shift1add256 --K 10 --manage
# python scripts/prepare_single.py --name 139442p0 --K 10 --index 0 --compute_strongest_interpolant --force_refresh
# python scripts/prepare_single.py --name 139442p0 --K 10 --index 1 --compute_strongest_interpolant --force_refresh
    # python scripts/AbsorptionExperiment.py --K 10 --category linear --main --use_minisat
    # python scripts/AbsorptionExperiment.py --K 10 --category exponential --main --use_minisat
    # python scripts/AbsorptionExperiment.py --K 10 --category linear --main --use_minisat --include_formula_in_checking
    # python scripts/AbsorptionExperiment.py --K 10 --category exponential --main --use_minisat --include_formula_in_checking
    # python scripts/AbsorptionExperiment.py --K 10 --category linear --main --include_formula_in_checking
    # python scripts/AbsorptionExperiment.py --K 10 --category exponential --main --include_formula_in_checking

    # python scripts/AbsorptionExperiment.py --K 10 --category linear --main 
    # python scripts/AbsorptionExperiment.py --K 10 --category exponential --main 
    # python scripts/AbsorptionExperiment.py --K 10 --category linear --main --use_glucose_proof --include_formula_in_checking
    # python scripts/AbsorptionExperiment.py --K 10 --category exponential --main --use_glucose_proof --include_formula_in_checking
    # python scripts/AbsorptionExperiment.py --K 10 --category linear --main --include_formula_in_checking
    # python scripts/AbsorptionExperiment.py --K 10 --category exponential --main --include_formula_in_checking
    # python scripts/AbsorptionExperiment.py --K 10 --category linear --main
    # python scripts/AbsorptionExperiment.py --K 10 --category exponential --main 

    # python scripts/AbsorptionExperiment.py --K 10 --category linear --main --use_minisat
    # python scripts/AbsorptionExperiment.py --K 10 --category linear --main
    # python eliminator.py --in test.cnf  --out test.custom_eliminator.out --elim-file test.localA --verbose
    # python scripts/sanity_check.py --K 10 --pddef 3 --all --manage > sanity_check_10.log
    # python scripts/sanity_check.py --K 5 --pddef 3 --all > sanity_check_def3_5.log
    # python scripts/sanity_check.py --K 15 --pddef 3 --all > sanity_check_def3_15.log
    # python scripts/sanity_check.py --K 40 --pddef 1 --all > sanity_check_40.log
    # python scripts/interpolant_sanity_check.py  --K 10 --pddef 3 --all > sanity_check_10_pddef3.log
    # python scripts/interpolant_sanity_check.py  --K 5 --pddef 3 --all > sanity_check_5_pddef3.log
fi

if [ "$section" == "4" ]; then
    python scripts/pipeline_scheduler.py  --category exponential --scaling --interpolation --proofgate
    python scripts/pipeline_scheduler.py  --category linear --scaling --interpolation --proofgate
fi

if [ "$section" == "5" ]; then
    # python scripts/pipeline_scheduler.py --prepare_formula --use_summary regression_summary.csv
    python scripts/PDSScalingExperiment.py --pddef 1 --category linear  --x K --trim_top_percent 90 --y pds
    python scripts/PDSScalingExperiment.py --pddef 1 --category linear  --x K --trim_top_percent 25 --y pds
    python scripts/PDSScalingExperiment.py --pddef 1 --category linear  --x K --trim_top_percent 15 --y pds
    python scripts/PDSScalingExperiment.py --pddef 1 --category linear  --x K --trim_top_percent 80 --y pds
    python scripts/PDSScalingExperiment.py --pddef 1 --category linear  --x K --trim_top_percent 70 --y pds
    python scripts/PDSScalingExperiment.py --pddef 1 --category linear  --x K --trim_top_percent 60 --y pds
    python scripts/PDSScalingExperiment.py --pddef 1 --category linear  --x K --trim_top_percent 50 --y pds
    python scripts/PDSScalingExperiment.py --pddef 1 --category linear  --x K --trim_top_percent 40 --y pds
    python scripts/PDSScalingExperiment.py --pddef 1 --category linear  --x K --trim_top_percent 30 --y pds
    python scripts/PDSScalingExperiment.py --pddef 1 --category linear  --x K --trim_top_percent 20 --y pds
    python scripts/PDSScalingExperiment.py --pddef 1 --category linear  --x K --trim_top_percent 10 --y pds
    # python scripts/prepare_data.py --compute_strongest_interpolant --name 139442p0 --K 3 --index 1
    # python scripts/sanity_check.py --K 5 --pddef 3 --all > sanity_check_def3_5.log
    # python scripts/sanity_check.py --K 20 --pddef 3 --all > sanity_check_def3_20.log
    # python scripts/prepare.py --prepare_scaling --manage
    # for f in ProofDoorBenchmark/interpolants_def3/10/*.interpolant; do
    #     python scripts/count_interpolant_byz3.py --file "$f" --pddef 3
    # done
fi

if [ "$section" == "6" ]; then
    #  python scripts/compute_resolution_steps.py --K 15 --manage
    # python scripts/prepare.py --permute_and_run --K 40
    # python scripts/PBHExperiment.py --K 40
    python scripts/PDSScalingExperiment.py --pddef 1 --category linear  --x K --trim_top_percent 5  --y pds
    python scripts/PDSScalingExperiment.py --pddef 3 --category both  --x K --trim_top_percent 5  --y pds
    python scripts/PDSScalingExperiment.py --pddef 1 --category both  --x n --trim_top_percent 5 --summary_csv scalington.csv --fixed_k 10 --y pds
    # python scripts/prepare.py --prepare_sequential --pddef 1 --K 40 --manage  --category linear --no_interpolant
    # python scripts/prepare.py --compute_strongest_interpolant 
    # python scripts/process_interpolants.py --K 40 --Solver minisat --CompareCombinedInstances --pddef 1 --UseCache --FormulaCategory exponential
fi

# scancel 46356867
# python scripts/prepare.py --prepare_sequential --pddef 1 --manage 
# python scripts/prepare.py --remove_absorption_result_caches_first --focus_name intel001
# cd ../
# rm ./ProofDoorBenchmark/interpolants/10/*
# rm ./ProofDoorBenchmark/smts/10/*
# mkdir newPDT
# cd newPDT/
# git clone git@github.com:ShiminZhang/ProofDoorTools.git
# cd ../ProofDoorTools/
# cp ../original/ProofDoorTools/ProofDoorBnchmark/aigs/* ProofDoorBenchmark/aigs/
# ./scripts/start_experiment.sh 40 all
# ./scripts/generate_minisat_proofs.sh 20
# python scripts/pyscripts/start_absorption_experiment.py --clean
# python scripts/combine_proofdoor_to_cnf.py 40 40
# sbatch ./scripts/manage_interpolant_jobs.sh 10 linear
# python check_uncomputed_PDS.py 60 6g
# ./scripts/start_experiment.sh 60 all
# rm ./ProofDoorBenchmark/smts/10/*.smt2
# mv ./ProofDoorBenchmark/cnfs/10/*.smt2 ./ProofDoorBenchmark/smts/10/
# sbatch ./manage_interpolant_jobs.sh 10
# sbatch scripts/manage_interpolant_jobs.sh 10 linear
# mv ./ProofDoorBenchmark/cnfs/40/ ./ProofDoorBenchmark/smts/40/
# ./scripts/start_experiment.sh 40
# source ../../../projects/def-vganesh/s568zhan/generall/bin/activate
# python process_interpolants.py --ToCNF --K 20 --ProcessInterpolantOnly
# sbatch scripts/remote_generate_combined_cnf.sh
# sleep 1h
# source ../../../projects/def-vganesh/s568zhan/generall/bin/activate
# python SMTCNFtoDIMACS.py ./ProofDoorBenchmark/interpolants/20/ 20

# ./scripts/run_combined_instances.sh ./ProofDoorBenchmark/interpolant_as_cnfs/dimacs/