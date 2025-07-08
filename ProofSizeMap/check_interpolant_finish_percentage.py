import os
import sys
import json
import tqdm

def main():
    # dir = "./ProofSizeMap/data/10/"
    combined_data = json.load(open("./ProofSizeMap/data_10.json", "r"))
    finished = []
    not_finished = []
    for file in tqdm.tqdm(combined_data.keys()):
        if combined_data[file][0] > 0:
                finished.append(file)
            else:
                not_finished.append(file)
    
    print(f"Finished: {len(finished)}")
    print(f"Not finished: {len(not_finished)}")
    print(f"Finished percentage: {len(finished) / (len(finished) + len(not_finished))}")
    
    json.dump(finished, open("finished.json", "w"))
    json.dump(not_finished, open("not_finished.json", "w"))
    pass

if __name__ == "__main__":
    main()