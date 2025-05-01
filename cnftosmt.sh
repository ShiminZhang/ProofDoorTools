#!/bin/bash

gen() {
    filename=$(basename $1)
    python ../CNFtoQFBV.py $1
    # sbatch --mem=32G -t 03:00:00 -o ./Outputs/${filename}.toSMT.log --wrap="source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python ../CNFtoQFBV.py $1"
}
k=$1
source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate
cd ./ProofDoorBenchmark/
rm *.log
for file in ./cnfs/${k}/*.cnf; do
    # echo $file
    if [ -f "$file" ]; then
        echo "Processing file: $file"
        gen $file
    fi
done
mkdir -p ./smts/${k}/   
mv ./cnfs/${k}/*.smt2 ./smts/${k}/
