import os
import json
import glob
import sys
def combine_json_files():
    k = sys.argv[1]
    # Path to the data directory
    data_dir = f"./ProofSizeMap/data/{k}"
    # Output file path
    output_file = "./ProofSizeMap/data.json"
    
    # Dictionary to store all combined data
    combined_data = {}
    
    # Find all JSON files in the data directory
    json_files = glob.glob(os.path.join(data_dir, "*.json"))
    
    # Read each JSON file and add its contents to the combined data
    for file_path in json_files:
        try:
            with open(file_path, 'r') as file:
                data = json.load(file)
                combined_data.update(data)
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
    
    # Write the combined data to the output file
    with open(output_file, 'w') as outfile:
        json.dump(combined_data, outfile, indent=2)
    
    print(f"Combined {len(json_files)} JSON files into {output_file}")

if __name__ == "__main__":
    combine_json_files()
