#!/bin/bash                                                    
#SBATCH --time=0-0:0:5300                                                      
#SBATCH --account=def-vganesh   
#SBATCH --mem=10g         

build=$1
suffix=$2
path=$3


if [ ! -f "$3" ] 
then
    echo "Formula $3 DOES NOT exist." 
    exit 1
fi

if [ ! -f "$build" ] 
then
    echo "build $build DOES NOT exist." 
    exit 1
fi


filename=$(basename $3)
LOG_FILE="./$path.$suffix.log"
test -f $LOG_FILE && rm $LOG_FILE
# exec > "$LOG_FILE" 2>&1
test -f $build && echo $build $suffix $path
time $build $path > $LOG_FILE
# $build $i
echo $suffix $LOG_FILE "${@:4}"
echo run $build $suffix $filename "${@:4}"

