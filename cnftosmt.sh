#!/bin/bash

gen() {
    filename=$(basename $1)
    sbatch -t 01:00:00 -o ./Outputs/${filename}.toSMT.log --wrap="source ../general/bin/activate; python ../CNFtoQFBV.py $1"
}
k=$1
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
