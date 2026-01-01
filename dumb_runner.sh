#!/bin/bash                                                    
#SBATCH --time=0-12:0:0                                                      
#SBATCH --account=def-vganesh 
#SBATCH --mem=20G
#SBATCH --cpus-per-task=1
#SBATCH --output=./dumb_runner_%j.log

section=$1
# git add -A; git commit -m "update"; git push
# sleep 2h
source ../../general/bin/activate
source .env

if [ "$section" == "1" ]; then
    python scripts/pipeline_scheduler.py --reverse  --category linear
    python scripts/pipeline_scheduler.py --reverse  --category exponential
    # python scripts/prepare.py --focus_name $2 --prepare_sequential --K $3
    # python scripts/AbsorptionExperiment.py --test
    #  python scripts/SMTTranslationToCNFExperiment.py --main --K 10 --category linear --time "8:00:00"
fi

if [ "$section" == "2" ]; then
    # python scripts/prepare.py --prepare_sequential --pddef 1 --manage --K 10 --category exponential,linear
    python ./scripts/prepare_single.py --name 6s399rb22 --K 100 --pre_interpolant --pddef 1 --force_refresh
    python scripts/SMTTranslationToCNFExperiment.py --K 100 --main --instance 6s399rb22
    # python scripts/sanity_check.py --K 5 --pddef 3 --all > sanity_check_def3_5.log
    # python scripts/sanity_check.py --K 15 --pddef 3 --all > sanity_check_def3_15.log
fi

if [ "$section" == "3" ]; then
    # python scripts/AbsorptionExperiment.py --K 10 --category linear --main --use_minisat
    # python scripts/AbsorptionExperiment.py --K 10 --category exponential --main --use_minisat
    # python scripts/AbsorptionExperiment.py --K 10 --category linear --main --use_minisat --include_formula_in_checking
    # python scripts/AbsorptionExperiment.py --K 10 --category exponential --main --use_minisat --include_formula_in_checking
    # python scripts/AbsorptionExperiment.py --K 10 --category linear --main --include_formula_in_checking
    # python scripts/AbsorptionExperiment.py --K 10 --category exponential --main --include_formula_in_checking

    # python scripts/AbsorptionExperiment.py --K 10 --category linear --main 
    # python scripts/AbsorptionExperiment.py --K 10 --category exponential --main 
    python scripts/AbsorptionExperiment.py --K 10 --category linear --main --use_glucose_proof --include_formula_in_checking
    python scripts/AbsorptionExperiment.py --K 10 --category exponential --main --use_glucose_proof --include_formula_in_checking
    python scripts/AbsorptionExperiment.py --K 10 --category linear --main --include_formula_in_checking
    python scripts/AbsorptionExperiment.py --K 10 --category exponential --main --include_formula_in_checking
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
    # ./simplecar -bmc -k 100 -cnf ProofDoorBenchmark/cnfs/100/ ProofDoorBenchmark/aigs/6s339rb22.aig
    # ./simplecar -bmc -k 1 -cnf ProofDoorBenchmark/cnfs/50/ ProofDoorBenchmark/aigs/6s339rb22.aig
    # python scripts/sanity_check.py --K 10 --pddef 1 --all > sanity_check_10.log
    # python scripts/sanity_check.py --K 40 --pddef 1 --all > sanity_check_40.log
    # python scripts/interpolant_sanity_check.py  --K 10 --pddef 1 --all > sanity_check_10_pddef1.log
    # python -m scripts.pyscripts.run_combined_formulas --k 40 --pddef 1 --category exponential
    #  python scripts/prepare_data.py --compute_strongest_interpolant --name 139442p0 --K 3 --index 1 --sanity_check 
     python scripts/prepare.py --focus_name 6s339rb22 --prepare_sequential --K 100 --manage
    # python scripts/run_combined_formulas.py --K 40 --pddef 1 --category exponential
fi

if [ "$section" == "5" ]; then
    python scripts/AbsorptionExperiment.py --test --use_pbh_proof 
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
    python scripts/PBHExperiment.py --K 40
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