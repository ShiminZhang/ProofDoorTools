import os
import shutil
import sys
from sys import argv
from utils.catagory import get_instance_list
# Define the three directories for different instance types
linear_instances = get_instance_list("linear")[0:103]
polynomial_instances = get_instance_list("polynomial")[0:100]
exponential_instances = get_instance_list("exponential")[0:100]


def check_progress(k, instance_type):
    Interpolant_DIR = f"ProofDoorBenchmark/interpolants/{k}/"
    
    if instance_type == "linear":
        instances = linear_instances
    elif instance_type == "polynomial":
        instances = polynomial_instances
    elif instance_type == "exponential":
        instances = exponential_instances

    total_instances = k * 100
    found_instances = 0
    for instance in instances:
        instance_dir = Interpolant_DIR
        for partition in range(k):
            interpolant_file = os.path.join(instance_dir, f"{instance}.{k}.{partition}.interpolant")
            # print(interpolant_file)
            if os.path.exists(interpolant_file):
                #print(f"Found {interpolant_file}")
                found_instances += 1
    print(f"Found {found_instances} interpolant files out of {total_instances} for {instance_type} instances")


if __name__ == "__main__":
    # separate_cnf_files(20)
    # k=int(argv[1])
    for k in [5,8,10,15]:
        print(f"Checking {k}")
        check_progress(k, "linear")
        check_progress(k, "polynomial")
        check_progress(k, "exponential")
    