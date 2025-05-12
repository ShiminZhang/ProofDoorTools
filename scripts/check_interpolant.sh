#!/bin/bash                                                    
#SBATCH --time=0-24:0:00                                                      
#SBATCH --account=def-vganesh   
#SBATCH --mem=20g         

testmode=false
if [ -z "$SLURM_JOB_ID" ]; then
    testmode=true
fi

linear_instances=(
    "139442p0"
    "139443p0"
    "139444p0"
    "139452p0"
    "139453p0"
    "139454p0"
    "139462p0"
    "139463p0"
    "139464p0"
    "6s159"
    "6s164"
    "6s362rb1"
    "6s372rb26"
    "6s384rb024"
    "6s385rb444"
    "6s391rb379"
    "6s4"
    "6s400rb07819"
    "6s421rb083"
    "6s515rb1"
    "beemcycschd3b1"
    "beemelev1f1"
    "beemfwt2b2"
    "beemfwt3f3"
    "beemlup1b1"
    "beemmcs6f1"
    "bj08amba2g1"
    "bj08aut82"
    "bjrb07amba1andenv"
    "bob9234specand"
    "bobmiterbm1and"
    "bobsynth09neg"
    "bobsynthand"
    "bobtuintand"
    "bobtuintorneg"
    "bobunr2p10d40l"
    "bobuns2p10d100l"
    "cal161"
    "cal37"
    "dspfilters_fastfir_second-p07"
    "eijks1196"
    "eijks1238"
    "eijks344"
    "eijks349"
    "eijks713"
    "frogs.5.prop1-func-interl"
    "gen10"
    "gen31"
    "gen35"
    "gen39"
    "gen43"
    "gen44"
    "intel037"
    "kenflashp03"
    "kenflashp04"
    "kenflashp07"
    "kenflashp08"
    "kenflashp09"
    "kenflashp10"
    "kenflashp13"
    "marlann_compute_cp_fail1-p2"
    "marlann_compute_cp_fail2-p0"
    "marlann_compute_cp_pass-p2"
    "mentorbm1or"
    "mentorbm1p01"
    "mentorbm1p09"
    "miim"
    "neclaftp1002"
    "neclaftp2001"
    "neclaftp2002"
)

polynomial_instances=(
    "6s173"
    "6s209b0"
    "6s317b14"
    "6s325rb072"
    "6s404rb1"
    "6s43"
    "beembrptwo3b2"
    "beemskbn3f1"
    "bj08amba2g3f3"
    "bob2"
    "bobcount"
    "boblivea"
    "boblivear"
    "bobtuint08neg"
    "bobtuint16neg"
    "bobtuint17neg"
    "bobtuint26neg"
    "cal4"
    "cal41"
    "cmuperiodic"
    "eijkbs4863"
    "eijks510"
    "eijks820"
    "eijks832"
    "eijks953"
    "elevator.4.prop1-func-interl"
    "gen12"
    "gen14"
    "h_TreeArb"
    "intel001"
    "intel066"
    "intersymbol_analog_estimation_convergence"
    "kenflashp01"
    "mentorbm1p02"
    "mentorbm1p05"
    "mentorbm1p07"
    "oc8051gm0caddr"
    "oc8051gm1edata"
    "oc8051gm2daddr"
    "oc8051gm36addr"
    "oc8051gm58addr"
    "oc8051gm68addr"
    "oc8051gmb8addr"
    "oc8051gmc5addr"
    "oc8051gmcadata"
    "oc8051gmfbaddr"
    "pdtswvtma6x4p1"
    "pdtviscoherence4"
    "pdtvisgigamax3"
    "pdtvisgigamax4"
    "pdtvissoap2"
    "pdtvisvending00"
    "pdtvisvending07"
    "picorv32-check-p12"
    "pj2018"
    "qspiflash_dualflexpress_divfive-p009"
    "qspiflash_dualflexpress_divfive-p116"
    "qspiflash_dualflexpress_divfive-p120"
    "qspiflash_dualflexpress_divfive-p126"
    "qspiflash_dualflexpress_divthree-p034"
    "qspiflash_dualflexpress_divthree-p068"
    "qspiflash_dualflexpress_divthree-p075"
    "qspiflash_dualflexpress_divthree-p094"
    "qspiflash_dualflexpress_divthree-p134"
    "qspiflash_dualflexpress_divthree-p153"
    "qspiflash_qflexpress_divfive-p063"
    "qspiflash_qflexpress_divfive-p067"
    "qspiflash_qflexpress_divfive-p100"
    "qspiflash_qflexpress_divfive-p107"
    "qspiflash_qflexpress_divfive-p121"
)

exponential_instances=(
    "6s0"
    "6s109"
    "6s194"
    "6s202b41"
    "6s204b19"
    "6s271rb045"
    "6s271rb079"
    "6s273b37"
    "6s275rb318"
    "6s277rb292"
    "6s288r"
    "6s306rb03"
    "6s307rb09"
    "6s326rb08"
    "6s342rb131"
    "6s344rb054"
    "6s355rb08740"
    "6s374b114"
    "6s38"
    "6s380b129"
    "6s403rb1342"
    "6s405rb611"
    "6s406rb067"
    "6s410rb043"
    "beemcmbrdg1f1"
    "beemlann2f1"
    "beemlifts2b1"
    "beemmsmie1f1"
    "beemptrsn4b1"
    "beemszmsk1f1"
    "beemtlphn4f1"
    "beemtrngt4b1"
    "bob05"
    "bob12s09"
    "bobsmoci"
    "bobtuint09neg"
    "bobtuint18neg"
    "bobtuint20neg"
    "cal102"
    "cal106"
    "cal112"
    "cal118"
    "cal119"
    "cal122"
    "cal140"
    "cal176"
    "cal21"
    "cal33"
    "cal99"
    "dspfilters_fastfir_second-p16"
    "dspfilters_fastfir_second-p21"
    "dspfilters_fastfir_second-p25"
    "eijkbs1512"
    "eijks1423"
    "eijks386"
    "eijks420"
    "eijks444"
    "intel020"
    "kenflashp11"
    "kenoopp1"
    "msmie.3.prop1-func-interl"
    "neclabakery001"
    "nusmvreactorp4"
    "oc8051gm12data"
    "oc8051gm15addr"
    "oc8051gmc6data"
    "oski15a01b04s"
    "oski15a01b05s"
    "oski15a01b10s"
    "oski15a01b11s"
)


# Get the array index
array_index=$SLURM_ARRAY_TASK_ID

# Get the list of SMT files
smt_path=$1
interpolant_path=$2
target_category=$3
# Extract k_value from the path
# Assuming the path format includes a directory named with the k_value (e.g., .../40/...)
k_value=$(echo "$smt_path" | grep -o '[0-9]\+' | tail -n 1)
# If k_value couldn't be extracted, set a default or exit with error
if [ -z "$k_value" ]; then
    echo "Error: Could not extract k_value from path. Please ensure the path contains a numeric directory."
    exit 1
fi

instance_index=$(($array_index / $k_value))
instance_partition_index=$(($array_index % $k_value))
echo $array_index matched to $instance_index $instance_partition_index at target category $target_category
echo $smt_path
echo $interpolant_path
echo $target_category
# Remove trailing slashes from paths
smt_path=${smt_path%/}
instance_basename=""
# Get the nth file from the list
smt_file=$(ls "$smt_path"/*.smt2 2>/dev/null | sed -n "${array_index}p")
# If target category is specified, filter files based on category
if [ ! -z "$target_category" ] && [ "$target_category" != "all" ]; then
    # Get the instance name based on the category and array index
    case "$target_category" in
        "linear")
            if [ $instance_index -le ${#linear_instances[@]} ]; then
                instance_basename="${linear_instances[$instance_index-1]}"
            else
                echo "instance_index $instance_index exceeds the number of linear instances"
                exit 0
            fi
            ;;
        "polynomial")
            if [ $instance_index -le ${#polynomial_instances[@]} ]; then
                instance_basename="${polynomial_instances[$instance_index-1]}"
            else
                echo "instance_index $instance_index exceeds the number of polynomial instances"
                exit 0
            fi
            ;;
        "exponential")
            if [ $instance_index -le ${#exponential_instances[@]} ]; then
                instance_basename="${exponential_instances[$instance_index-1]}"
            else
                echo "instance_index $instance_index exceeds the number of exponential instances"
                exit 0
            fi
            ;;
        *)
            echo "Unknown category: $target_category"
            exit 1
            ;;
    esac
    
    # Find the SMT file that matches the instance name
    smt_file=$(find "$smt_path" -name "${instance_basename}*${instance_partition_index}.smt2" | head -n 1)
else
    # Get the nth file from the list (original behavior)
    smt_file=$(ls "$smt_path"/*.smt2 2>/dev/null | sed -n "${array_index}p")
fi



if [ -z "$smt_file" ]; then
    echo "No file found for array index $array_index $instance_partition_index $instance_index $instance_name $target_category $k_value"
    exit 0
fi
echo $smt_file
# Extract the instance name from the file path
instance_name=$(basename "$smt_file" .smt2)

if [ ! -f "$smt_file" ]; then
    echo "Formula $smt_file DOES NOT exist." 
    exit 1
fi

# module load python/3.10
# module load scipy-stack
# source ../venv/bin/activate
# If in test mode, echo all paths and exit
if [ "$testmode" = true ]; then
    echo "Test mode active. Displaying all paths:"
    echo "SMT path: $smt_path"
    echo "Instance name: $instance_name"
    echo "SMT file: $smt_file"
    echo "Interpolant path: $interpolant_path"
    echo "Current directory: $(pwd)"
    exit 0
fi

# Generate interpolant and record time used
start_time=$(date +%s)
interpolant_file="$interpolant_path/$instance_name.interpolant"
echo $interpolant_file
if [ ! -f "$interpolant_file" ] || [ ! -s "$interpolant_file" ]; then
    echo "Interpolant file $interpolant_file does not exist. Generating..."
    ./z3 "$smt_file" > "$interpolant_file"
else
    echo "Interpolant file $interpolant_file exists. Skipping generation."
    exit 0
fi
end_time=$(date +%s)
time_taken=$((end_time - start_time))
echo "Time taken to generate interpolant for $instance_name: $time_taken seconds"
# echo to json file

# Check if time taken is less than 6 hours (21600 seconds)
if [ $time_taken -lt 21600 ]; then
    file="$interpolant_path/$instance_name.interpolant"
    if [ -f "$file" ]; then
        echo "Processing $file"
        base_name=$(basename $file .interpolant)
    fi
fi
end_time=$(date +%s)
# echo to json file
echo "{\"instance_name\": \"$instance_name\", \"time_taken\": $time_taken}" > "./ProofDoorBenchmark/data/PDComputationTime/${instance_basename}.${k_value}.${instance_partition_index}.json"

# Check if time taken is less than 6 hours (21600 seconds)
if [ $time_taken -lt 21600 ]; then

    file="$interpolant_path/$instance_name.interpolant"

    if [ -f "$file" ]; then
        echo "Processing $file"
        base_name=$(basename $file .interpolant)
        smt_file="${smt_path}/${base_name}.smt2"
        source ../general/bin/activate
        python ./scripts/separate_profile_from_interpolant.py $file
        python3 ./scripts/count_interpolant_byz3.py $file --smt $smt_file --save --timeout -1
        deactivate
    fi
fi
