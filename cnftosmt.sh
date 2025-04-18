#!/bin/bash

gen() {
    filename=$(basename $1)
    python ../CNFtoQFBV.py $1
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
mv ./cnfs/${k}/*.smt2 ./smts/${k}/
