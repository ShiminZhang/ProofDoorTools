import os
import json
import glob
from tqdm import tqdm
import sys
import argparse

def combine_json_files(k,pddef):
    pddef = 1
    data_dir = f"./ProofSizeMap/data/pddef_{pddef}/{k}"

    output_file = f"./ProofSizeMap/data/pddef_1/data_{k}.json"
    combined_data = {}
    json_files = glob.glob(os.path.join(data_dir, "*.json"))
    for file_path in tqdm(sorted(json_files)):
        try:
            with open(file_path, 'r') as file:
                data = json.load(file)
                # basename = os.path.basename(file_path)
                combined_data.update(data)

        except Exception as e:
            print(f"Error processing {file_path}: {e}")
    # print(combined_data)
    # exit()
    with open(output_file, 'w') as outfile:
        json.dump(combined_data, outfile, indent=2)
    
    print(f"Combined {len(json_files)} JSON files into {output_file}")
    
def main():
    # parser = argparse.ArgumentParser(description='Combine JSON files')
    # parser.add_argument('--k', type=int, help='k value')
    # parser.add_argument('--pddef', type=int, help='pddef')
    # args = parser.parse_args()
    for k in range(1,21,1):
        combine_json_files(k,1)

if __name__ == "__main__":
    main()
