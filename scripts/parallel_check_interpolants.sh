k=$1
interpolants_dir="ProofDoorBenchmark/interpolants/${k}/"
smt_dir="ProofDoorBenchmark/smts/${k}/"

source ../general/bin/activate
for file in ${interpolants_dir}/*.interpolant; do
    echo "Processing $file"
    base_name=$(basename $file .interpolant)
    smt_file="${smt_dir}/${base_name}.smt2"
    sbatch --mem=30G --time=2:00:00 --output="ProofDoorBenchmark/logs/${base_name}.computePDsize.log" --wrap="source ../general/bin/activate; python3 count_interpolant_byz3.py $file --smt $smt_file --save; deactivate"
done
