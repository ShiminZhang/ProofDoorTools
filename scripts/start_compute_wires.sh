#! /bin/bash

cnf_path=$1

source ../general/bin/activate
python3 compute_wires.py --cnf_path $cnf_path
deactivate
