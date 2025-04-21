#!/bin/bash

gen() {
    filename=$(basename $1)
    python ../CNFtoQFBV_sanity.py $1
}
k=$1
for file in ./test/interpolant_sanity/cnfs/*.cnf; do
    # echo $file
    if [ -f "$file" ]; then
        echo "Processing file: $file"
        gen $file
    fi
done
mv ./test/interpolant_sanity/*.smt2 ./test/interpolant_sanity/smts/
