#!/bin/bash

gen() {
    filename=$(basename $1)
    # sbatch -t 01:00:00 -o ./Outputs/${filename}.toSMT.log --wrap="python ../CNFtoQFBV_sanity.py $1"
    python ../CNFtoQFBV_sanity.py $1
}
mkdir -p ./interpolant_sanity/smts/
for file in ./interpolant_sanity/cnfs/*.cnf; do
    # echo $file
    if [ -f "$file" ]; then
        echo "Processing file: $file"
        gen $file
    fi
done
mv ./interpolant_sanity/cnfs/*.sanity.smt2 ./interpolant_sanity/smts/
