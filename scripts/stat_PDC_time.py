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
        if "DUE TO TIME LIMIT" in content:
            # Interpolant file ./ProofDoorBenchmark/interpolants/60//6s109.60.45.interpolant does not exist.
            # The matched part should be 6s109.60.45
            # Extract benchmark name from the error message for timeout cases
            # Example: If the interpolant file path is ./ProofDoorBenchmark/interpolants/60/6s109.60.45.interpolant
            # The benchmark name should be 6s109.60.45
            timeout_match = re.search(r'Interpolant file \./ProofDoorBenchmark/interpolants/\d+//(\w+\.\d+\.\d+)\.interpolant', content)
            if timeout_match:
                benchmark_name = timeout_match.group(1)
                return benchmark_name, "timeout"
        return None, None
    except Exception as e:
        print(f"Error processing {output_file}: {e}")
        return None, None

def main():
    # Path to output files
    output_dir = "Outputs"
    output_files = glob.glob(os.path.join(output_dir, "compute_interpolant_*.out"))
    
    # Dictionary to store benchmark times
    benchmark_times = {}
    
    # Process each output file
    for output_file in tqdm(output_files):
        benchmark_name, time_seconds = extract_time_from_output(output_file)
        if benchmark_name is None:
            print(f"No benchmark name found in {output_file}")
            continue
        else:
            print(f"In {output_file} found {benchmark_name} with time {time_seconds} seconds")
        parts = benchmark_name.split(".")
        basename = parts[0]
        k_value = parts[1]
        partition_index = parts[2]
        # if benchmark_name and time_seconds and not isinstance(time_seconds, str):
        benchmark_times[benchmark_name] = time_seconds
        json_file = f"./ProofDoorBenchmark/data/PDComputationTime/{k_value}/{basename}.{k_value}.{partition_index}.json"
        if time_seconds == 0 and os.path.exists(json_file):
            with open(json_file, 'r') as f:
                data = json.load(f)
            print(f"Current time is 0, In {json_file} found {benchmark_name} with time {data['time_taken']} seconds")
            if data['time_taken'] == 0:
                os.remove(json_file)
            continue
        # echo "{\"instance_name\": \"$instance_name\", \"time_taken\": $time_taken}" > "./ProofDoorBenchmark/data/PDComputationTime/interpolant_times.json"
        
        with open(json_file, 'w') as f:
            json.dump({"instance_name": benchmark_name, "time_taken": time_seconds}, f)
    
    # Calculate statistics
    stats = []
    for benchmark, times in benchmark_times.items():
        if times:
            time_after_panelty = times
            is_timeout = False
            if isinstance(times, str):
                time_after_panelty = 24*60*60
                is_timeout = True
            stats.append({
                'Instance': benchmark,
                'Time': time_after_panelty,
                'Timeout': is_timeout
            })
    # Save statistics to CSV file
    if stats:
        stats.sort(key=lambda x: x['Instance'])
        stats_df = pd.DataFrame(stats)
        
        stats_df.to_csv('benchmark_times.csv', index=False)
        print(f"Statistics saved to 'benchmark_times.csv'")
        print("No timing data found in the output files.")

if __name__ == "__main__":
    main()
