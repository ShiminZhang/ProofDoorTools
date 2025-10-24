from count_interpolant_byz3 import count_resolution_steps
import argparse
from utils.catagory import get_instance_list
import os
import time

def get_queue_size():
    return int(os.popen("squeue -u $USER -h -r -t RUNNING,PENDING | wc -l").read())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--K", type=int, required=True)
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument("--name", type=str, default=None)
    parser.add_argument("--manage", action="store_true", required=False)
    args = parser.parse_args()

    if args.manage:
        instance_list = get_instance_list("all")
        limit = 1000
        batch_size = 10
        index = 0
        while index < batch_size * len(instance_list):
            queue_size = get_queue_size()
            print(f"Queue size: {queue_size}, Index: {index}")
            while get_queue_size() < limit - batch_size and index < batch_size * len(instance_list):
                name = instance_list[index // batch_size]
                for interpolant_index in range(args.K):
                    activate_python = "source ../general/bin/activate"
                    os.makedirs("./SlurmLogs/compute_resolution_steps", exist_ok=True)
                    wrapped = f"{activate_python} && python ./scripts/compute_resolution_steps.py --name {name} --K {args.K} --index {interpolant_index}"
                    os.system(f"sbatch --job-name=cr_{name}.{args.K}.{interpolant_index} --output=./SlurmLogs/compute_resolution_steps/{name}.{args.K}.{interpolant_index}.log --mem=16g --time=6:00:00 --wrap=\"{wrapped}\"")
                index += batch_size
            print(f"Updated Index: {index}, Queue size: {get_queue_size()}")
            time.sleep(300)
        # for name in instance_list:
        #     for index in range(args.K):
        #         activate_python = "source ../general/bin/activate"
        #         os.makedirs("./SlurmLogs/compute_resolution_steps", exist_ok=True)
        #         wrapped = f"{activate_python} && python ./scripts/compute_resolution_steps.py --name {name} --K {args.K} --index {index}"
        #         os.system(f"sbatch --job-name=cr_{name}.{args.K}.{index} --output=./SlurmLogs/compute_resolution_steps/{name}.{args.K}.{index}.log --mem=16g --time=6:00:00 --wrap=\"{wrapped}\"")
    else:
        count_resolution_steps(args.name,args.K,args.index)

if __name__ == "__main__":
    main()