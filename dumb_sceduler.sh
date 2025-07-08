#!/bin/bash                                                    
#SBATCH --time=0-8:0:0                                                      
#SBATCH --account=def-vganesh 
#SBATCH --mem=16G


git add -A; git commit -m "update"; git push
# source ../general/bin/activate
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