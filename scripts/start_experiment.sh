#!/bin/bash                                                    
#SBATCH --time=0-0:0:5000                                                      
#SBATCH --account=def-vganesh   
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
    "neclaftp4001"
    "neclaftp4002"
    "neclaftp5001"
    "neclatcas1a001"
    "nusmvguidancep6"
    "nusmvguidancep8"
    "nusmvreactorp1"
    "nusmvreactorp5"
    "nusmvreactorp6"
    "nusmvsyncarb10p2"
    "nusmvsyncarb5p2"
    "nusmvtcasp2"
    "nusmvtcasp3"
    "nusmvtcastp3"
    "oski15a01b20s"
    "oski15a10b00s"
    "oski15a14b14s"
    "oski15a14b16s"
    "oski15a14b32s"
    "oski1rub03i"
    "oski2b2i"
    "paper_v3"
    "pdtpmsam2901"
    "pdtpmsarbiter"
    "pdtpmsblackjack"
    "pdtpmsrotate32"
    "pdtpmstwo"
    "pdtpmsusbphy"
    "pdtswvtms12x8p1"
    "pdtvisblackjack0"
    "pdtvisblackjack1"
    "pdtvisblackjack2"
    "pdtvisgray0"
    "pdtvishuffman1"
    "pdtvisminmax0"
    "pdtvisminmaxr1"
    "pdtvisns2p3"
    "pdtvisretherrtf1"
    "pdtvisvsa16a10"
    "pdtvisvsa16a16"
    "pdtvisvsa16a27"
    "pdtvisvsar22"
    "pdtvsar8multip13"
    "pdtvsar8multip16"
    "pdtvsar8multip23"
    "pdtvsarmultip08"
    "pdtvsarmultip13"
    "pdtvsarmultip29"
    "pdtvsarmultip30"
    "picorv32-check-p09"
    "picorv32-check-p20"
    "pj2002"
    "power2eq65536"
    "power2sum128"
    "power2sum256"
    "power2sum32"
    "qspiflash_dualflexpress_divfive-p022"
    "qspiflash_dualflexpress_divfive-p128"
    "qspiflash_dualflexpress_divfive-p143"
    "qspiflash_dualflexpress_divfive-p164"
    "qspiflash_dualflexpress_divthree-p046"
    "qspiflash_dualflexpress_divthree-p143"
    "qspiflash_dualflexpress_divthree-p158"
    "qspiflash_qflexpress_divfive-p017"
    "qspiflash_qflexpress_divfive-p036"
    "qspiflash_qflexpress_divfive-p048"
    "qspiflash_qflexpress_divfive-p064"
    "rast-p01"
    "rast-p04"
    "rast-p21"
    "shift1add2048"
    "shift1add256"
    "shift1add262144"
    "texasparsesysp2"
    "vcegar_QF_BV_ar"
    "vcegar_QF_BV_itc99_b13_p10"
    "vgasim_imgfifo-p066"
    "vgasim_imgfifo-p082"
    "vgasim_imgfifo-p105"
    "viselevatorp3"
    "visprodcellp01"
    "zipcpu-busdelay-p15"
    "zipcpu-busdelay-p43"
    "zipcpu-pfcache-p02"
    "zipcpu-pfcache-p13"
    "zipcpu-pfcache-p20"
    "zipcpu-pfcache-p27"
    "zipcpu-pfcache-p28"
    "zipcpu-zipmmu-p31"
    "zipcpu-zipmmu-p39"
    "zipversa_composecrc_prf-p00"
    "zipversa_composecrc_prf-p07"
    "zipversa_composecrc_prf-p11"
    "zipversa_composecrc_prf-p17"
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
    "qspiflash_qflexpress_divfive-p137"
    "rast-p00"
    "rast-p11"
    "texaspimainp12"
    "vgasim_imgfifo-p093"
    "vis_arrays_am2910_p2"
    "vis_arrays_am2910_p3"
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
    "oski15a01b22s"
    "oski15a01b24s"
    "oski15a01b56s"
    "pdtpmscoherence"
    "pdtpmsns2"
    "pdtvisgoodbakery0"
    "pdtvisns3p02"
    "pdtvistwoall3"
    "pgm_protocol.7.prop1-back-serstep"
    "picorv32-check-p05"
    "pj2016"
    "qspiflash_dualflexpress_divfive-p007"
    "qspiflash_dualflexpress_divfive-p050"
    "qspiflash_dualflexpress_divfive-p092"
    "qspiflash_dualflexpress_divfive-p127"
    "qspiflash_dualflexpress_divfive-p133"
    "qspiflash_dualflexpress_divfive-p136"
    "qspiflash_dualflexpress_divfive-p161"
    "qspiflash_dualflexpress_divthree-p005"
    "qspiflash_dualflexpress_divthree-p007"
    "qspiflash_dualflexpress_divthree-p012"
    "qspiflash_dualflexpress_divthree-p069"
    "qspiflash_dualflexpress_divthree-p076"
    "qspiflash_dualflexpress_divthree-p106"
    "qspiflash_dualflexpress_divthree-p124"
    "qspiflash_dualflexpress_divthree-p136"
    "qspiflash_dualflexpress_divthree-p141"
    "qspiflash_dualflexpress_divthree-p161"
    "qspiflash_dualflexpress_divthree-p164"
    "qspiflash_qflexpress_divfive-p029"
    "qspiflash_qflexpress_divfive-p038"
    "qspiflash_qflexpress_divfive-p104"
    "qspiflash_qflexpress_divfive-p113"
    "qspiflash_qflexpress_divfive-p122"
    "vgasim_imgfifo-p064"
    "vgasim_imgfifo-p099"
    "vis4arbitp1"
    "zipcpu-busdelay-p00"
    "zipcpu-busdelay-p36"
    "zipcpu-busdelay-p46"
    "zipcpu-pfcache-p01"
    "zipcpu-pfcache-p22"
    "zipcpu-pfcache-p24"
    "zipcpu-zipmmu-p26"
)



declare -A K_map=(
[6s0]="10"
[139442p0]="10"
[139443p0]="10"
[139444p0]="10"
[139453p0]="10"
[139452p0]="10"
[139454p0]="10"
)

get_k_value() {
    local key=$1
    if [[ -n "${K_map[$key]}" ]]; then
        echo "${K_map[$key]}"
    else
        echo "10"
    fi
}


solvers=(
    "cadical"
    "minisat"
    )

suffixs=(
    "cadical"
    "minisat"
)

# benchmark=(
# "./ProofDoorBenchmark/cnfs/"
# )

# Get the length of the array
linear_instances_l=${#linear_instances[@]}
exponential_instances_l=${#exponential_instances[@]}
polynomial_instances_l=${#polynomial_instances[@]}
solvers_l=${#solvers[@]}
suffixs_l=${#suffixs[@]}
scratch_benchmark_path="./ProofDoorBenchmark/"

echo "____________________________________________________________________________________________________" >> ./running/runningjobs.log
categories=(
    "linear"
    "exponential"
    "polynomial"
)

# Create destination directories if they don't exist
for category in "${categories[@]}"; do
    mkdir -p "./ProofDoorBenchmark/${category}"
done

# Process linear instances
mkdir -p ./ProofDoorBenchmark/interpolants/$1/
mkdir -p ${scratch_benchmark_path}/smts/$1/
mkdir -p ./ProofDoorBenchmark/linear/$1/
mkdir -p ./ProofDoorBenchmark/polynomial/$1/
mkdir -p ./ProofDoorBenchmark/exponential/$1/

# Check if second argument is provided, if not provided, create interpolants only
# Check if the first argument (k value) is provided
if [ -z "$1" ]; then
    echo "Error: First argument (k value) is required"
    echo "Usage: $0 <k_value> [category]"
    exit 1
fi

# If only k value is provided, create interpolants only
if [ -n "$1" ] && [ -z "$2" ]; then
    echo "Only k value provided. Creating interpolants only..."
    # Process all interpolants
    echo "Processing all interpolants..."

    # for (( i=0; i<linear_instances_l; i++ )); do
    #     name=${linear_instances[$i]}
    #     # k_value=$(get_k_value $name)
    #     k_value=$1
    #     cnf_path=./ProofDoorBenchmark/cnfs/$k_value/$name.$k_value.cnf
    #     mkdir -p ./ProofDoorBenchmark/smtsoi/$k_value/
    #     for (( j=0; j<k_value; j++ )); do
    #         smt_path=./ProofDoorBenchmark/smts/$k_value/$name.$k_value.$j.smt2
    #         if [ -f "$smt_path" ]; then
    #             cp $smt_path ./ProofDoorBenchmark/smtsoi/$k_value/$name.$k_value.$j.smt2
    #         fi
    #     done
    # done 

    # for (( i=0; i<polynomial_instances_l; i++ )); do
    #     name=${polynomial_instances[$i]}
    #     # k_value=$(get_k_value $name)
    #     k_value=$1
    #     cnf_path=./ProofDoorBenchmark/cnfs/$k_value/$name.$k_value.cnf
    #     mkdir -p ./ProofDoorBenchmark/smtsoi/$k_value/
    #     for (( j=0; j<k_value; j++ )); do
    #         smt_path=./ProofDoorBenchmark/smts/$k_value/$name.$k_value.$j.smt2
    #         if [ -f "$smt_path" ]; then
    #             cp $smt_path ./ProofDoorBenchmark/smtsoi/$k_value/$name.$k_value.$j.smt2
    #         fi
    #     done
    # done 

    # for (( i=0; i<exponential_instances_l; i++ )); do
    #     name=${exponential_instances[$i]}
    #     # k_value=$(get_k_value $name)
    #     k_value=$1
    #     cnf_path=./ProofDoorBenchmark/cnfs/$k_value/$name.$k_value.cnf
    #     mkdir -p ./ProofDoorBenchmark/smtsoi/$k_value/
    #     for (( j=0; j<k_value; j++ )); do
    #         smt_path=./ProofDoorBenchmark/smts/$k_value/$name.$k_value.$j.smt2
    #         if [ -f "$smt_path" ]; then
    #             cp $smt_path ./ProofDoorBenchmark/smtsoi/$k_value/$name.$k_value.$j.smt2
    #         fi
    #     done
    # done 

    count=0
    
    # Submit array job for interpolant checking
    jobid=$(sbatch --priority 0 -o ./Outputs/interpolant_%A_%a.out ./scripts/check_interpolant.sh ${scratch_benchmark_path}/smts/$1/ ${scratch_benchmark_path}/interpolants/$1/ | awk '{print $4}')
    echo "Submitted array job with ID: $jobid" >> ./running/runningjobs.log
    echo "Submitted array job with ID: $jobid"

    echo "Interpolant creation complete."
    exit 0
fi

if [ -z "$2" ]; then
    echo "Error: Second argument (category) is required"
    echo "Usage: $0 <k_value> <category>"
    echo "Category must be one of: linear, exponential, polynomial, all"
    exit 1
fi

# Convert to lowercase for case-insensitive comparison
category=$(echo "$2" | tr '[:upper:]' '[:lower:]')

# Validate category argument
case $category in
    linear|exponential|polynomial|all)
        # Valid category
        ;;
    *)
        echo "Error: Invalid category '$2'"
        echo "Category must be one of: linear, exponential, polynomial, all"
        exit 1
        ;;
esac

# Skip processing sections based on category
if [ "$category" != "linear" ] && [ "$category" != "all" ]; then
    linear_instances=()
    linear_instances_l=0
fi

if [ "$category" != "exponential" ] && [ "$category" != "all" ]; then
    exponential_instances=()
    exponential_instances_l=0
fi

if [ "$category" != "polynomial" ] && [ "$category" != "all" ]; then
    polynomial_instances=()
    polynomial_instances_l=0
fi


# if [ "$category" != "polynomial" ] && [ "$category" != "all" ]; then
#     interpolants_l=0
# fi





for (( i=0; i<linear_instances_l; i++ )); do
    name=${linear_instances[$i]}
    # k_value=$(get_k_value $name)
    k_value=$1
    cnf_path=./ProofDoorBenchmark/cnfs/$k_value/$name.$k_value.cnf
    dest_path=./ProofDoorBenchmark/linear/$k_value/$name.$k_value.cnf
    # sbatch --priority 0 -o ./Outputs/output_%A_%a.out ./scripts/check_interpolant.sh $name.$k_value ./ProofDoorBenchmark/smts/$k_value/ ./ProofDoorBenchmark/interpolants/$k_value/
    
    # Copy file if it doesn't exist in destination
    if [ ! -f "$dest_path" ]; then
        cp "$cnf_path" "$dest_path"
        echo "Copied $cnf_path to $dest_path"
    else
        echo "File already exists: $dest_path"
    fi
    
    # Submit solver jobs for this instance
    for (( j=0; j<solvers_l; j++ )); do
        build=./solvers/${solvers[$j]}
        suffix=${suffixs[$j]}
        
        jobid=$(sbatch --priority 0 -o ./Outputs/output_%A_%a.out ./scripts/submit_solver.sh $build ${suffix} $dest_path | awk '{print $4}')
        echo "Submitted job with ID: $jobid" ${suffix} $dest_path $build >> ./running/runningjobs.log
        echo "Submitted job with ID: $jobid" ${suffix} $dest_path $build
    done
done

for (( i=0; i<polynomial_instances_l; i++ )); do
    name=${polynomial_instances[$i]}
    # k_value=$(get_k_value $name)
    k_value=$1
    cnf_path=./ProofDoorBenchmark/cnfs/$k_value/$name.$k_value.cnf
    dest_path=./ProofDoorBenchmark/polynomial/$k_value/$name.$k_value.cnf
    # sbatch --priority 0 -o ./Outputs/output_%A_%a.out ./scripts/check_interpolant.sh $name.$k_value ./ProofDoorBenchmark/smts/$k_value/ ./ProofDoorBenchmark/interpolants/$k_value/
    
    # Copy file if it doesn't exist in destination
    if [ ! -f "$dest_path" ]; then
        cp "$cnf_path" "$dest_path"
        echo "Copied $cnf_path to $dest_path"
    else
        echo "File already exists: $dest_path"
    fi
    
    # Submit solver jobs for this instance
    for (( j=0; j<solvers_l; j++ )); do
        build=./solvers/${solvers[$j]}
        suffix=${suffixs[$j]}
        
        jobid=$(sbatch --priority 0 -o ./Outputs/output_%A_%a.out ./scripts/submit_solver.sh $build ${suffix} $dest_path | awk '{print $4}')
        echo "Submitted job with ID: $jobid" ${suffix} $dest_path $build >> ./running/runningjobs.log
        echo "Submitted job with ID: $jobid" ${suffix} $dest_path $build
    done
done

for (( i=0; i<exponential_instances_l; i++ )); do
    name=${exponential_instances[$i]}
    # k_value=$(get_k_value $name)
    k_value=$1
    cnf_path=./ProofDoorBenchmark/cnfs/$k_value/$name.$k_value.cnf
    dest_path=./ProofDoorBenchmark/exponential/$k_value/$name.$k_value.cnf
    # sbatch --priority 0 -o ./Outputs/output_%A_%a.out ./scripts/check_interpolant.sh $name.$k_value ./ProofDoorBenchmark/smts/$k_value/ ./ProofDoorBenchmark/interpolants/$k_value/
    
    # Copy file if it doesn't exist in destination
    if [ ! -f "$dest_path" ]; then
        cp "$cnf_path" "$dest_path"
        echo "Copied $cnf_path to $dest_path"
    else
        echo "File already exists: $dest_path"
    fi
    
    # Submit solver jobs for this instance
    for (( j=0; j<solvers_l; j++ )); do
        build=./solvers/${solvers[$j]}
        suffix=${suffixs[$j]}
        
        jobid=$(sbatch --priority 0 -o ./Outputs/output_%A_%a.out ./scripts/submit_solver.sh $build ${suffix} $dest_path | awk '{print $4}')
        echo "Submitted job with ID: $jobid" ${suffix} $dest_path $build >> ./running/runningjobs.log
        echo "Submitted job with ID: $jobid" ${suffix} $dest_path $build
    done
done