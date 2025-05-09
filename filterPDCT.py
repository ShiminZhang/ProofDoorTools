import os
import glob
import shutil
import re

def rename_json_files():
    # Base directory for PDComputationTime
    base_dir = "ProofDoorBenchmark/data/PDComputationTime/"
    
    # Find all subdirectories (K values)
    # k_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    k_dirs = [base_dir]
    print(f"Found {len(k_dirs)} K-value directories")
    
    # Process each K directory
    for k_dir in k_dirs:
        # k_path = os.path.join(base_dir, k_dir)
        k_path = base_dir
        # Find all JSON files in this directory
        json_files = glob.glob(os.path.join(k_path, "*.*.json"))
        
        print(f"Found {len(json_files)} JSON files in {k_path}")
        
        # Process each JSON file
        for json_file in json_files:
            # Extract the filename
            filename = os.path.basename(json_file)
            
            # Parse the filename to get components
            match = re.match(r"(.*?)\.(\d+)\.json", filename)
            if match:
                base_name = match.group(1)
                # k_value = match.group(2)
                partition_index = match.group(2)
                
                # Create new filename with k_value set to 60
                new_filename = f"{base_name}.60.{partition_index}.json"
                new_filepath = os.path.join(f"{k_path}/60", new_filename)
                
                # Rename the file
                if filename != new_filename:
                    print(f"Renaming {filename} to {new_filename}")
                    shutil.move(json_file, new_filepath)

if __name__ == "__main__":
    rename_json_files()
    print("File renaming completed.")
