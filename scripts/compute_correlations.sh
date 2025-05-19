# sbatch --wrap --mem 20G "source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python process_interpolants.py --K 80 --UseCache --Solver minisat --FormulaCategory exponential --UseCache > ./logs/minisat_exponential_80.log"
# sbatch --wrap --mem 20G "source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python process_interpolants.py --K 80 --UseCache --Solver minisat --FormulaCategory linear --UseCache > ./logs/minisat_linear_80.log"
# sbatch --wrap --mem 20G "source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python process_interpolants.py --K 80 --UseCache --Solver minisat --FormulaCategory polynomial --UseCache > ./logs/minisat_polynomial_80.log"

# sbatch --wrap --mem 20G "source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python process_interpolants.py --K 80 --UseCache --Solver cadical --FormulaCategory exponential --UseCache > ./logs/cadical_exponential_80.log"
# sbatch --wrap --mem 20G "source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python process_interpolants.py --K 80 --UseCache --Solver cadical --FormulaCategory linear --UseCache > ./logs/cadical_linear_80.log"
# sbatch --wrap --mem 20G "source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python process_interpolants.py --K 80 --UseCache --Solver cadical --FormulaCategory polynomial --UseCache > ./logs/cadical_polynomial_80.log"

# sbatch --wrap --mem 20G "source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python process_interpolants.py --K 10 --UseCache --Solver minisat --FormulaCategory exponential --UseCache > ./logs/minisat_exponential_10.log"
# sbatch --wrap --mem 20G "source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python process_interpolants.py --K 10 --UseCache --Solver minisat --FormulaCategory linear --UseCache > ./logs/minisat_linear_10.log"
# sbatch --wrap --mem 20G "source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python process_interpolants.py --K 10 --UseCache --Solver minisat --FormulaCategory polynomial --UseCache > ./logs/minisat_polynomial_10.log"

# sbatch --wrap --mem 20G "source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python process_interpolants.py --K 10 --UseCache --Solver cadical --FormulaCategory exponential --UseCache > ./logs/cadical_exponential_10.log"
# sbatch --wrap --mem 20G "source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python process_interpolants.py --K 10 --UseCache --Solver cadical --FormulaCategory linear --UseCache > ./logs/cadical_linear_10.log"
# sbatch --wrap --mem 20G "source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python process_interpolants.py --K 10 --UseCache --Solver cadical --FormulaCategory polynomial --UseCache > ./logs/cadical_polynomial_10.log"
# Function to run all correlations locally without sbatch
extra_args=""

run_correlations_locally() {
    local k_values=(60)
    local solvers=("minisat" "cadical")
    local categories=("exponential" "linear" "polynomial")
    mkdir -p ./CausalAnalysisLogs
    for k in "${k_values[@]}"; do
        for solver in "${solvers[@]}"; do
            for category in "${categories[@]}"; do
                echo "Running correlation for K=${k}, Solver=${solver}, Category=${category}"
                source ../general/bin/activate
                python scripts/process_interpolants.py --K ${k} --UseCache --Solver ${solver} --FormulaCategory ${category} ${extra_args} > ./CausalAnalysisLogs/${solver}_${category}_${k}.log
                echo "Completed ${solver}_${category}_${k}"
            done
        done
    done
    
    echo "All correlation computations completed"
}
# Function to submit all correlation jobs using sbatch
submit_correlation_jobs() {
    local k_values=(10 80)
    local solvers=("minisat" "cadical")
    local categories=("exponential" "linear" "polynomial")
    
    for k in "${k_values[@]}"; do
        for solver in "${solvers[@]}"; do
            for category in "${categories[@]}"; do
                echo "Submitting job for K=${k}, Solver=${solver}, Category=${category}"
                sbatch --wrap "source /home/s568zhan/projects/def-vganesh/s568zhan/generall/bin/activate; python process_interpolants.py --K ${k} --SkipInterpolant --Solver ${solver} --FormulaCategory ${category} > ./logs/${solver}_${category}_${k}.log" --mem 20G
                echo "Submitted ${solver}_${category}_${k}"
            done
        done
    done
    
    echo "All correlation jobs submitted"
}

# To run all correlations locally, uncomment the following line:
run_correlations_locally

# python process_interpolants.py --K 20 --UseCache --Solver minisat --FormulaCategory exponential
# python process_interpolants.py --K 20 --UseCache --Solver minisat --FormulaCategory linear
# python process_interpolants.py --K 20 --UseCache --Solver minisat --FormulaCategory polynomial

# python process_interpolants.py --K 20 --UseCache --Solver cadical --FormulaCategory exponential
# python process_interpolants.py --K 20 --UseCache --Solver cadical --FormulaCategory linear
# python process_interpolants.py --K 20 --UseCache --Solver cadical --FormulaCategory polynomial