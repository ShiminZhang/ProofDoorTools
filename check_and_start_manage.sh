#!/bin/bash
time=$(date +%s)
mkdir -p progress/
mv managing.log managing.$time.log
k_value=$1
category=$2

file_count=$(ls ./ProofDoorBenchmark/smts/$k_value/ | wc -l)
echo "File count: $file_count" >> progress.log
empty_file_count=$(find ./ProofDoorBenchmark/smts/$k_value/ -type f -empty | wc -l)
echo "Empty SMT2 count: $empty_file_count" >> progress.log
interpolants_file_count=$(ls ./ProofDoorBenchmark/interpolants/$k_value/ | wc -l)
echo "Interpolant file count: $interpolants_file_count" >> progress.log
empty_interpolant_file_count=$(find ./ProofDoorBenchmark/interpolants/$k_value/ -type f -empty | wc -l)
echo "Empty interpolant file count: $empty_interpolant_file_count" >> progress.log
PDS_count=$(ls ./ProofSizeMap/data/$k_value/ | wc -l)
echo "PDS count: $PDS_count" >> progress.log
PDC_count=$(ls ./ProofDoorBenchmark/data/PDComputationTime/$k_value/ | wc -l)
echo "PDC count: $PDC_count" >> progress.log

mv progress.log progress.$time.log
mv managing.$time.log progress/
mv progress.$time.log progress/
sbatch ./scripts/manage_interpolant_jobs.sh $k_value $category