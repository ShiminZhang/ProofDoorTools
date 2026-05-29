#!/bin/bash                                                    
#SBATCH --time=0-8:0:0                                                      
#SBATCH --account=def-vganesh 
#SBATCH --mem=20G
source .env
source $PYENVPATH
# Function to check if required directories exist and create them if needed
check_and_create_dirs() {
    local dirs=("pds_st_correlation")
    
    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            echo "Creating directory: $dir"
            mkdir -p "$dir"
        fi
    done
}

# Function to run a single experiment with error handling
run_experiment() {
    local focus_name=$1
    local output_file="pds_st_correlation/${focus_name}.out"
    
    echo "Starting experiment for: $focus_name"
    
    python scripts/process_interpolants.py \
        --K 10 \
        --UseCache \
        --Solver cadicalplain \
        --FocusName "$focus_name" \
        > "$output_file"
}

# Function to run all experiments
run_all_experiments() {
    local focus_names=("6s" "beem" "bob" "eijks" "gen" "intel" "kenflash" "mentor" "neclaft" "nusmv" "oc805" "oski15" "pdt" "qspiflash") 
    
    echo "Starting batch experiments..."
    echo "=================================="
    
    for focus_name in "${focus_names[@]}"; do
        run_experiment "$focus_name"
        echo "----------------------------------"
    done
    
    echo "All experiments completed!"
}

# Main execution
echo "Initializing experiment environment..."
check_and_create_dirs

echo "Starting experiments..."
# run_all_experiments
# python scripts/process_interpolants.py --AllK --Solver cadicalplain --UseCache --FormulaCategory linear --ExcludeParse > pds_st_correlation/all_K_linear.st_pds_cor_exclude_parse
# python scripts/process_interpolants.py --AllK --Solver cadicalplain --UseCache --FormulaCategory polynomial --ExcludeParse > pds_st_correlation/all_K_polynomial.st_pds_cor_exclude_parse
# python scripts/process_interpolants.py --AllK --Solver cadicalplain --UseCache --FormulaCategory exponential --ExcludeParse > pds_st_correlation/all_K_exponential.st_pds_cor_exclude_parse

# python scripts/process_interpolants.py --AllK --Solver cadicalplain --UseCache --FormulaCategory linear > pds_st_correlation/all_K_linear.st_pds_cor
# python scripts/process_interpolants.py --AllK --Solver cadicalplain --UseCache --FormulaCategory polynomial > pds_st_correlation/all_K_polynomial.st_pds_cor
# python scripts/process_interpolants.py --AllK --Solver cadicalplain --UseCache --FormulaCategory exponential > pds_st_correlation/all_K_exponential.st_pds_cor

# python scripts/process_interpolants.py --AllK --Solver cadicalplain --UseCache > pds_st_correlation/all_K.st_pds_cor
# python scripts/process_interpolants.py --K 5 --Solver cadicalplain --UseCache > pds_st_correlation/K_5.st_pds_cor
# python scripts/process_interpolants.py --K 8 --Solver cadicalplain --UseCache > pds_st_correlation/K_8.st_pds_cor
# python scripts/process_interpolants.py --K 10 --Solver cadicalplain --UseCache > pds_st_correlation/K_10.st_pds_cor
# python scripts/process_interpolants.py --K 40 --Solver cadicalplain --UseCache > pds_st_correlation/K_40.st_pds_cor
# python scripts/process_interpolants.py --K 40 --Solver cadicalplain --UseCache --FormulaCategory linear > pds_st_correlation/K_40_linear.st_pds_cor
# python scripts/process_interpolants.py --K 40 --Solver cadicalplain --UseCache --FormulaCategory polynomial > pds_st_correlation/K_40_polynomial.st_pds_cor
# python scripts/process_interpolants.py --K 40 --Solver cadicalplain --UseCache --FormulaCategory exponential > pds_st_correlation/K_40_exponential.st_pds_cor

# python scripts/process_interpolants.py --AllK --Solver cadicalplain --UseCache --ExcludeParse > pds_st_correlation/all_K.st_pds_cor_exclude_parse
# python scripts/process_interpolants.py --K 5 --Solver cadicalplain --UseCache --ExcludeParse > pds_st_correlation/K_5.st_pds_cor_exclude_parse
# python scripts/process_interpolants.py --K 8 --Solver cadicalplain --UseCache --ExcludeParse > pds_st_correlation/K_8.st_pds_cor_exclude_parse
# python scripts/process_interpolants.py --K 10 --Solver cadicalplain --UseCache --ExcludeParse > pds_st_correlation/K_10.st_pds_cor_exclude_parse
# python scripts/process_interpolants.py --K 40 --Solver cadicalplain --UseCache --ExcludeParse > pds_st_correlation/K_40.st_pds_cor_exclude_parse


# python scripts/process_interpolants.py --K 5 --Solver cadicalplain --UseCache --pddef 1 > pds_st_correlation/pddef_1/K_5.st_pds_cor
# python scripts/process_interpolants.py --K 8 --Solver cadicalplain --UseCache --pddef 1 > pds_st_correlation/pddef_1/K_8.st_pds_cor
# python scripts/process_interpolants.py --K 10 --Solver cadicalplain --UseCache --pddef 1 > pds_st_correlation/pddef_1/K_10.st_pds_cor
# python scripts/process_interpolants.py --K 15 --Solver cadicalplain --UseCache --pddef 1 > pds_st_correlation/pddef_1/K_15.st_pds_cor
# python scripts/process_interpolants.py --K 20 --Solver cadicalplain --UseCache --pddef 1 > pds_st_correlation/pddef_1/K_20.st_pds_cor
# python scripts/process_interpolants.py --K 40 --Solver cadicalplain --UseCache --pddef 1 > pds_st_correlation/pddef_1/K_40.st_pds_cor
# python scripts/process_interpolants.py --AllK --Solver cadicalplain --UseCache --pddef 1 > pds_st_correlation/pddef_1/all_K.st_pds_cor_exclude_parse

# python ProofSizeMap/combine_json.py --pddef 3 --k 10
# python ProofSizeMap/combine_json.py --pddef 3 --k 15
# python ProofSizeMap/combine_json.py --pddef 3 --k 5

# python ProofSizeMap/combine_json.py --pddef 1 --k 10
# python ProofSizeMap/combine_json.py --pddef 1 --k 5
# python ProofSizeMap/combine_json.py --pddef 1 --k 8
# python ProofSizeMap/combine_json.py --pddef 1 --k 20
# python ProofSizeMap/combine_json.py --pddef 1 --k 15

# python scripts/process_interpolants.py --K 5 --Solver cadicalplain --UseCache --pddef 3 > pds_st_correlation/pddef_3/K_5.st_pds_cor
# python scripts/process_interpolants.py --K 5 --Solver cadicalplain --UseCache --FormulaCategory linear --pddef 3 > pds_st_correlation/pddef_3/K_5_linear.st_pds_cor
# python scripts/process_interpolants.py --K 5 --Solver cadicalplain --UseCache --FormulaCategory polynomial --pddef 3 > pds_st_correlation/pddef_3/K_5_polynomial.st_pds_cor
# python scripts/process_interpolants.py --K 5 --Solver cadicalplain --UseCache --FormulaCategory exponential --pddef 3 > pds_st_correlation/pddef_3/K_5_exponential.st_pds_cor

# python scripts/process_interpolants.py --K 10 --Solver cadicalplain --UseCache --pddef 3 > pds_st_correlation/pddef_3/K_10.st_pds_cor
# python scripts/process_interpolants.py --K 10 --Solver cadicalplain --UseCache --FormulaCategory linear --pddef 3 > pds_st_correlation/pddef_3/K_10_linear.st_pds_cor
# python scripts/process_interpolants.py --K 10 --Solver cadicalplain --UseCache --FormulaCategory polynomial --pddef 3 > pds_st_correlation/pddef_3/K_10_polynomial.st_pds_cor
# python scripts/process_interpolants.py --K 10 --Solver cadicalplain --UseCache --FormulaCategory exponential --pddef 3 > pds_st_correlation/pddef_3/K_10_exponential.st_pds_cor

# python scripts/process_interpolants.py --K 15 --Solver cadicalplain --UseCache --pddef 3 > pds_st_correlation/pddef_3/K_15.st_pds_cor
# python scripts/process_interpolants.py --K 15 --Solver cadicalplain --UseCache --FormulaCategory linear --pddef 3 > pds_st_correlation/pddef_3/K_15_linear.st_pds_cor
# python scripts/process_interpolants.py --K 15 --Solver cadicalplain --UseCache --FormulaCategory polynomial --pddef 3 > pds_st_correlation/pddef_3/K_15_polynomial.st_pds_cor
# python scripts/process_interpolants.py --K 15 --Solver cadicalplain --UseCache --FormulaCategory exponential --pddef 3 > pds_st_correlation/pddef_3/K_15_exponential.st_pds_cor

# INSERT_YOUR_CODE
# for f in ProofDoorBenchmark/interpolants_def3/10/*.interpolant; do
#     python scripts/count_interpolant_byz3.py --file "$f" --pddef 3
# done

# python scripts/count_interpolant_byz3.py --file ProofDoorBenchmark/interpolants_def3/10/6s0.10.0.interpolant  --pddef 3

python scripts/process_interpolants.py --K 10 --pddef 3 --Solver cadicalplain --UseCache --FormulaCategory valid > out_valid.log
python scripts/process_interpolants.py --K 10 --pddef 3 --Solver cadicalplain --UseCache --FormulaCategory exponential > out_exponential.log
python scripts/process_interpolants.py --K 10 --pddef 3 --Solver cadicalplain --UseCache --FormulaCategory polynomial > out_polynomial.log
python scripts/process_interpolants.py --K 10 --pddef 3 --Solver cadicalplain --UseCache --FormulaCategory linear > out_linear.log
python scripts/process_interpolants.py --K 10 --pddef 3 --Solver cadicalplain --UseCache --FormulaCategory all > out_all.log


