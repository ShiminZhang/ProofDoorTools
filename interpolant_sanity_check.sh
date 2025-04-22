#!/bin/bash

k=$1
source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate
mkdir -p ./test/interpolant_sanity/results
for file in ./test/interpolant_sanity/smts/*.sanity.smt2; do
    basename=$(basename $file .sanity.smt2)
    interpolant_file=./test/interpolant_sanity/interpolants/$basename.interpolant
    if [ ! -f "$interpolant_file" ]; then
        echo "not found: $interpolant_file"
    fi
    result_file=./test/interpolant_sanity/results/$basename.result
    python interpolant_sanity_check.py $file $interpolant_file > $result_file
done
