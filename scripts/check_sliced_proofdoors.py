import os
import json
from utils.utils import GetData
from utils.paths import get_CNF_dir
from scipy.stats import t


def main():
    # get all the files in the sliced_proofdoors folder
    k_value = 40
    solver = "cadical"
    combined_cnfs_dir = "./ProofDoorBenchmark/combined_cnfs/"
    original_cnfs_dir = get_CNF_dir(k_value)
    original_data,original_instance_time_map,par2,_ = GetData(original_cnfs_dir,solver, True)
    combined_data,combined_instance_time_map,par2,_ = GetData(combined_cnfs_dir,solver, True)
    print(len(combined_instance_time_map))
    print(len(original_instance_time_map))
    # Sort instance_time_map by key
    for key, value in sorted(combined_instance_time_map.items()):
        print(f"{key} :: {value}")
    
    sorted_instance_time_map = dict(sorted(combined_instance_time_map.items()))
    original_combined_map = {}
    basenames = set()
    # ignore_basenames = set(["beembrptwo3b2","dspfilters_fastfir_second-p16"])
    # print(original_instance_time_map)
    for key, value in combined_instance_time_map.items():
        basename = key.split(".")[0]
        # if basename not in ignore_basenames:
        basenames.add(basename)
        
    for basename in basenames:
        original_combined_map[basename] = {}
        cnf_key = basename + f".{k_value}.cnf.{solver}.log"
        original_combined_map[basename][0] = original_instance_time_map[cnf_key]
        for i in range(1,k_value + 1):
            combined_key = basename + f".{k_value}.combined.{i}.cnf.{solver}.log"
            if combined_key in combined_instance_time_map:
                original_combined_map[basename][i] = combined_instance_time_map[combined_key]
            
    with open(f"slicedexp_{solver}.json", "w") as f:
        json.dump(original_combined_map, f, indent=4)
    print(original_combined_map)
    print(sorted_instance_time_map)

    # Check if times are growing with index for each basename and perform regression
    for basename, times in original_combined_map.items():
        print(f"\nAnalyzing {basename}:")
        
        # Prepare data for regression
        indices = sorted(times.keys())
        values = [times[idx] for idx in indices]
        # Calculate correlation coefficient
        n = len(indices)
        sum_x = sum(indices)
        sum_y = sum(values)
        sum_xy = sum(x * y for x, y in zip(indices, values))
        sum_xx = sum(x * x for x in indices)
        
        if n > 1:
            mean_x = sum_x / n
            mean_y = sum_y / n
            
            # Calculate numerator and denominator for correlation
            numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(indices, values))
            denominator_x = sum((x - mean_x) ** 2 for x in indices)
            denominator_y = sum((y - mean_y) ** 2 for y in values)
            
            # Calculate correlation coefficient
            correlation = numerator / ((denominator_x * denominator_y) ** 0.5)
            # Calculate p-value using t-test
            t_stat = correlation * ((n-2)/(1-correlation**2))**0.5
            p_value = 2 * (1 - t.cdf(abs(t_stat), n-2))
            print(f"  P-value: {p_value:.4f}")
            print(f"  Correlation coefficient: {correlation:.4f}")
            
            # Interpret correlation
            if abs(correlation) > 0.7:
                strength = "strong"
            elif abs(correlation) > 0.3:
                strength = "moderate"
            else:
                strength = "weak"
                
            if correlation > 0:
                direction = "positive"
            else:
                direction = "negative"
                
            print(f"  {strength} {direction} correlation")
        else:
            print(f"  Not enough data points for correlation analysis")
        # Calculate linear regression
        n = len(indices)
        if n > 1:  # Need at least 2 points for regression
            sum_x = sum(indices)
            sum_y = sum(values)
            sum_xy = sum(x * y for x, y in zip(indices, values))
            sum_xx = sum(x * x for x in indices)
            
            # Calculate slope and intercept
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
            intercept = (sum_y - slope * sum_x) / n
            
            print(f"  Linear regression: y = {slope:.4f}x + {intercept:.4f}")
            print(f"  R-squared: {slope * slope:.4f}")
            
            # Check if times are growing
            is_growing = slope > 0
            if is_growing:
                print(f"  Times are increasing (positive slope)")
            else:
                print(f"  Times are decreasing (negative slope)")
        else:
            print(f"  Not enough data points for regression")
        # Overall correlation analysis
        print("\nOverall correlation analysis:")
        all_indices = []
        all_values = []
        for instance_name, data in original_combined_map.items():
            indices = [int(k) for k in data.keys()]
            values = list(data.values())
            all_indices.extend(indices)
            all_values.extend(values)
        
        n = len(all_indices)
        if n > 1:
            mean_x = sum(all_indices) / n
            mean_y = sum(all_values) / n
            
            numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(all_indices, all_values))
            denominator_x = sum((x - mean_x) ** 2 for x in all_indices)
            denominator_y = sum((y - mean_y) ** 2 for y in all_values)
            
            correlation = numerator / ((denominator_x * denominator_y) ** 0.5)
            t_stat = correlation * ((n-2)/(1-correlation**2))**0.5
            p_value = 2 * (1 - t.cdf(abs(t_stat), n-2))
            
            print(f"  Overall P-value: {p_value:.4f}")
            print(f"  Overall correlation coefficient: {correlation:.4f}")
            
            if abs(correlation) > 0.7:
                strength = "strong"
            elif abs(correlation) > 0.3:
                strength = "moderate"
            else:
                strength = "weak"
                
            if correlation > 0:
                direction = "positive"
            else:
                direction = "negative"
                
            print(f"  Overall {strength} {direction} correlation")
            
            # Overall linear regression
            sum_x = sum(all_indices)
            sum_y = sum(all_values)
            sum_xy = sum(x * y for x, y in zip(all_indices, all_values))
            sum_xx = sum(x * x for x in all_indices)
            
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
            intercept = (sum_y - slope * sum_x) / n
            
            print(f"  Overall linear regression: y = {slope:.4f}x + {intercept:.4f}")
            print(f"  Overall R-squared: {slope * slope:.4f}")
        else:
            print("  Not enough data points for overall correlation analysis")
    


if __name__ == "__main__":
    main()