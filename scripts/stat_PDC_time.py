import os
import re
import glob
import pandas as pd
from collections import defaultdict
import json
from tqdm import tqdm

def extract_time_from_output(output_file):
    """Extract interpolant generation time from output file."""
    try:
        with open(output_file, 'r') as f:
            content = f.read()
            
        # Look for time information in the output
        time_match = re.search(r'Time taken to generate interpolant for ([\w.]+): (\d+) seconds', content)
        if time_match:
            benchmark_name = time_match.group(1)
            time_seconds = int(time_match.group(2))
            return benchmark_name, time_seconds
        
        return None, None
    except Exception as e:
        print(f"Error processing {output_file}: {e}")
        return None, None

def main():
    # Path to output files
    output_dir = "Outputs"
    output_files = glob.glob(os.path.join(output_dir, "compute_interpolant_*.out"))
    
    # Dictionary to store benchmark times
    benchmark_times = defaultdict(list)
    
    # Process each output file
    for output_file in tqdm(output_files):
        benchmark_name, time_seconds = extract_time_from_output(output_file)
        if benchmark_name is None:
            print(f"No benchmark name found in {output_file}")
            continue
        parts = benchmark_name.split(".")
        basename = parts[0]
        k_value = parts[1]
        partition_index = parts[2]
        if benchmark_name and time_seconds:
            benchmark_times[benchmark_name].append(time_seconds)
        json_file = f"./ProofDoorBenchmark/data/PDComputationTime/{basename}.{k_value}.{partition_index}.json"
        # echo "{\"instance_name\": \"$instance_name\", \"time_taken\": $time_taken}" > "./ProofDoorBenchmark/data/PDComputationTime/interpolant_times.json"
        
        with open(json_file, 'w') as f:
            json.dump({"instance_name": benchmark_name, "time_taken": time_seconds}, f)
    
    # Calculate statistics
    stats = []
    for benchmark, times in benchmark_times.items():
        if times:
            stats.append({
                'Benchmark': benchmark,
                'Min Time (s)': min(times),
                'Max Time (s)': max(times),
                'Avg Time (s)': sum(times) / len(times),
                'Count': len(times)
            })
    # Save statistics to CSV file
    if stats:
        stats_df = pd.DataFrame(stats)
        stats_df.to_csv('benchmark_times.csv', index=False)
        print(f"Statistics saved to 'benchmark_times.csv'")
        print("No timing data found in the output files.")

if __name__ == "__main__":
    main()
