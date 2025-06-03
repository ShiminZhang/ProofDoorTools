#!/bin/bash                                                    
#SBATCH --time=0-8:0:0                                                      
#SBATCH --account=def-vganesh 
#SBATCH --mem=20G
sleep 2h
# source ../general/bin/activate
./scripts/start_experiment.sh 40 all
# python scripts/combine_proofdoor_to_cnf.py 40 40
# sbatch ./scripts/manage_interpolant_jobs.sh 10 linear
# python check_uncomputed_PDS.py 60 6g
# ./scripts/start_experiment.sh 60 all
# sleep 2h
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