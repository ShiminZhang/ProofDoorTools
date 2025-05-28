import json
import os
import glob
import argparse
def get_wire_sizes(k):
    # Get all wire files in the benchmark directory
    wire_files = glob.glob(f"./ProofDoorBenchmark/wires/{k}/*.wires.json", recursive=True)
    wire_sizes = {}
    for wire_file in wire_files:
        with open(wire_file, 'r') as f:
            data = json.load(f)
            wire_sizes[wire_file] = data['wire_size']
    
    # Sort wire sizes in increasing order
    sorted_sizes = dict(sorted(wire_sizes.items(), key=lambda x: x[1]))
    print("Wire sizes in increasing order:")
    for file_path, size in sorted_sizes.items():
        print(f"{file_path}: {size}")
    
    print("\nDumping to sorted_wire_sizes.json...")
    print(sorted_sizes)
    
    json.dump(sorted_sizes, open(f"sorted_wire_sizes_{k}.json", "w"), indent=4)
    return sorted_sizes
    # Process each wire file
    for wire_file in wire_files:
        with open(wire_file, 'r') as f:
            data = json.load(f)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()
    get_wire_sizes(args.k)
