#!/bin/bash                                                    
#SBATCH --time=0-8:0:0                                                      
#SBATCH --account=def-vganesh 
#SBATCH --mem=20G


interested_names=(
    "6s326rb08"
    "beembrptwo3b2"
    "beemcycschd3b1"
    )

for name in ${interested_names[@]}; do
    for i in {0..10}; do
        echo $name $i
        ./z3 ./ProofDoorBenchmark/smts/10/$name.10.$i.smt2 > ./ProofDoorBenchmark/interpolants/10/$name.10.$i.interpolant
    done
done