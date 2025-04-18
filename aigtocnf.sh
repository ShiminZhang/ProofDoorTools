#!/bin/bash

gen() {
    filename=$(basename $1)
    sbatch --wrap "./../simplecar -bmc -k $2 -cnf ./cnfs/${2}/ $1"
}

cd ./ProofDoorBenchmark/
mkdir ./cnfs/$1/
for file in ./aigs/*.aig; do
    # echo $file
    if [ -f "$file" ]; then
        echo "Processing file: $file"
        gen $file $1
    fi
done
