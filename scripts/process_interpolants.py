import os
from count_interpolant_lines import count_lines
from count_interpolant_byz3 import count_lines_byz3
import glob
import json         
import re
from tqdm import tqdm
import argparse
import numpy as np
import pandas as pd
from PDC_analysis import get_PDC_time
from utils.process_cnf import compute_cnf_size_for_category
from utils.utils import GetData
from collections import defaultdict
from utils.utils import ComputeCorrelation,RewriteMap,PolynomialRegression
from utils.process_cnf import compute_N_map


def process_interpolants(k_path,to_cnf=False):
    interpolants_dir = f"ProofDoorBenchmark/interpolants/{k_path}"
    smts_dir = f"ProofDoorBenchmark/smts/{k_path}"
    results_map = {}
    if not os.path.exists(interpolants_dir):
        print(f"Error: Directory '{interpolants_dir}' not found.")
        return
    
    # Get all files in the directory
    files = [f for f in os.listdir(interpolants_dir) if f.endswith('.interpolant')]
    
    if not files:
        print(f"No .interpolant files found in '{interpolants_dir}'")
        return
    
    print("File\t\t\tSize")
    print("-" * 40)
    
    for file in sorted(files):
        smt_path = os.path.join(smts_dir, file.replace('.interpolant', '.smt2'))
        file_path = os.path.join(interpolants_dir, file)
        # line_count, let_count = count_lines_byz3(file_path)
        # if line_count == 0 and let_count == 0:
        #     continue
        
        # proofdoor_size = line_count + let_count - 3
        proofdoor_size = count_lines_byz3(file_path,smt_path,to_cnf)
        print(f"{file}\t{proofdoor_size}")
        results_map[file] = proofdoor_size
    
    return results_map

def ComputeCNFvsInterpolantSizeRatio(CNFMap,InterpolantMap):
    # Compute the ratio of the size of the CNF to the size of the interpolant
    # Use the Pearson correlation coefficient
    common_keys = [key for key in CNFMap if key in InterpolantMap]
    cnf_sizes = [CNFMap[key] for key in common_keys]
    interpolant_sizes = [InterpolantMap[key] for key in common_keys]
    print(f"Average interpolant size: {sum(interpolant_sizes) / len(interpolant_sizes)}")
    print(f"Average matched CNF size: {sum(cnf_sizes) / len(cnf_sizes)}")
    print(f"number of matched instances: {len(common_keys)}")
    ratio = [cnf_sizes[i] / interpolant_sizes[i] for i in range(len(common_keys))]
    print(ratio)
    return ratio
    
if __name__ == "__main__":
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Process interpolants')
    parser.add_argument('--UseCache', action='store_true', help='Use cached data if available')
    parser.add_argument('--UseLogCache', action='store_true', help='Use cached data if available')
    parser.add_argument('--UseInterpolantCache', action='store_true', help='Use cached data if available')
    parser.add_argument('--UseCNFCache', action='store_true', help='Use cached data if available')
    parser.add_argument('--ProcessLogOnly', action='store_true', help='Use cached data if available')
    parser.add_argument('--ProcessInterpolantOnly', action='store_true', help='Use cached data if available')
    parser.add_argument('--SkipInterpolant', action='store_true', help='Use cached data if available')
    parser.add_argument('--CompareCombinedInstances', action='store_true', help='Use cached data if available')
    parser.add_argument('--Solver', type=str, default='cadical', help='SAT solver to use')
    parser.add_argument('--K', type=int, default=80, help='K value')
    parser.add_argument('--EstimatePDSize', action='store_true', help='Estimate PD size')
    parser.add_argument('--FormulaCategory', type=str, default='linear', help='Formula category')
    parser.add_argument('--CheckCNFvsInterpolantSizeRatio', action='store_true', help='Check CNF vs Interpolant Size Ratio')
    parser.add_argument('--ToCNF', action='store_true', help='Convert to CNF')
    parser.add_argument('--CheckInterpolantCNFSizeCorrelation', action='store_true', help='Check Interpolant CNF size correlation')
    parser.add_argument('--CheckPDCSolvingTimeCorrelation', action='store_true', help='Check PDC solving time correlation')
    parser.add_argument('--CheckFormulaSizeNCorrelation', action='store_true', help='Check formula size N correlation')
    parser.add_argument('--FitPolynomialRegressionOnFormulaSize', type=int, default=-1, help='Fit polynomial regression on formula size')
    parser.add_argument('--FitPolynomialRegressionOnPDSize', type=int, default=-1, help='Fit polynomial regression on PD size')
    # Parse arguments
    args = parser.parse_args()
    use_cache = args.UseCache 
    solver = args.Solver
    check_cnf_vs_interpolant_size_ratio = args.CheckCNFvsInterpolantSizeRatio
    K = args.K
    formula_category = args.FormulaCategory
    if args.ProcessInterpolantOnly:
        results_map = process_interpolants(K,args.ToCNF)
        with open(f'ProofDoorBenchmark/interpolants/{K}/interpolant_sizes.txt', 'w') as f:
            for file, size in results_map.items():
                f.write(f"{file}\t{size}\n")
        exit()
        
    # If use_cache is True, try to read the interpolants map from file
    if use_cache or args.SkipInterpolant or args.UseInterpolantCache and os.path.exists('./ProofSizeMap/data.json'):
        print("Using cached interpolant sizes from file")
        results_map = {}
        data = json.load(open(f'./ProofSizeMap/data_{K}.json', 'r'))
        for key, value in data.items():
            k_value = key.split('.')[1]
            if k_value != str(K):
                continue
            results_map[key] = value
        # with open(f'ProofDoorBenchmark/interpolants/{K}/interpolant_sizes.txt', 'r') as f:
        #     for line in f:
        #         parts = line.strip().split('\t')
        #         if len(parts) == 2:
        #             file_name, size_tuple = parts
        #             # Parse the tuple string "(90, 'UNSAT')" to get just the size
        #             size = int(size_tuple.split(',')[0].strip('('))
        #             results_map[file_name] = size
        if results_map:
            print("Loaded cached interpolant sizes")
    elif not args.ProcessLogOnly:
        results_map = process_interpolants(K,args.ToCNF)
    # print(results_map)
    
    # Write results to a file
    if not args.ProcessLogOnly and not args.UseCache:
        with open(f'ProofDoorBenchmark/interpolants/{K}/interpolant_sizes.txt', 'w') as f:
            for file, size in results_map.items():
                f.write(f"{file}\t{size}\n")
    
    cadical_data,cadical_map,cadical_par2,cadical_mem = GetData(f"./ProofDoorBenchmark/{formula_category}/{K}/", solver, args.UseLogCache or use_cache)

    # print(cadical_map)
            
    # Rewrite cadical_map with keys' first part before "."
    rewritten_cadical_map = {}
    for key, value in cadical_map.items():
        # Extract the first part of the key before the first "."
        key_parts = key.split('.')
        new_key = key_parts[0]
        rewritten_cadical_map[new_key] = value
    
    if args.CompareCombinedInstances:
        combined_data,combined_map,combined_par2,combined_mem = GetData(f"./ProofDoorBenchmark/combined/{formula_category}/", solver, False)
        # print(cadical_map)
        # print(combined_map)
        for key in combined_map:
            rewritten_key = key.split('.')[0]
            if rewritten_key in rewritten_cadical_map:
                print(f"{key} {combined_map[key]} {rewritten_cadical_map[rewritten_key]}")
        exit()
    # Rewrite results_map (interpolants map) with keys' first part before "."
    proof_door_size_map = {}
    interpolant_size_map = results_map
    skip_keys = []
    max_interpolant_size = {}
    for key, value in results_map.items():
        key_parts = key.split('.')
        new_key = key_parts[0]
        max_interpolant_size[new_key] = max(max_interpolant_size.get(new_key, 100), value[0])
    
    for key, value in results_map.items():
        # Extract the first part of the key before the first "."
        if key in skip_keys:
            continue
        key_parts = key.split('.')
        new_key = key_parts[0]
        k_value = key_parts[1]
        value=value[0]
        if value < 0:
            if args.EstimatePDSize:
                value = max_interpolant_size[new_key]
            else:
                skip_keys.append(key)
                continue
        if new_key not in proof_door_size_map:
            proof_door_size_map[new_key] = value
        else:
            proof_door_size_map[new_key] += value
    # Preparations done ------------------------------------------------------------

    # analysis ---------------------------------------------------------------------
    if args.CheckFormulaSizeNCorrelation:
        # TODO do a regression analysis
        print("-" * 100)
        print(f"Checking formula size correlation for K={K}")
        cnf_sizes = compute_cnf_size_for_category(formula_category,K,args.UseCNFCache or use_cache)
        N_of_literals = compute_N_map(K,args.UseCNFCache or use_cache)
        cnf_sizes = RewriteMap(cnf_sizes)
        N_of_literals = RewriteMap(N_of_literals)
        ComputeCorrelation(N_of_literals, cnf_sizes,NameLeft="N of literals",NameRight="Formula Size")
        exit()
        
    if args.FitPolynomialRegressionOnFormulaSize >= 0:
        print("-" * 100)
        print(f"Fitting polynomial regression on formula size for K={K}")
        cnf_sizes = compute_cnf_size_for_category(formula_category,K,args.UseCNFCache or use_cache)
        N_of_literals = compute_N_map(K,args.UseCNFCache or use_cache)
        cnf_sizes = RewriteMap(cnf_sizes)
        N_of_literals = RewriteMap(N_of_literals)
        polynomial = PolynomialRegression(N_of_literals, cnf_sizes,degree=args.FitPolynomialRegressionOnFormulaSize)
        print(polynomial)
        exit()

    if args.FitPolynomialRegressionOnPDSize >= 0:
        print("-" * 100)
        print(f"Fitting polynomial regression on PD size for K={K}")
        proof_door_size_map = RewriteMap(proof_door_size_map)
        
        N_of_literals = compute_N_map(K,args.UseCNFCache or use_cache)
        N_of_literals = RewriteMap(N_of_literals)
        polynomial = PolynomialRegression(N_of_literals, proof_door_size_map,degree=args.FitPolynomialRegressionOnPDSize)
        print(polynomial)
        exit()

    if args.CheckPDCSolvingTimeCorrelation:
        print("-" * 100)
        print(f"Checking PDC solving time correlation for K={K}")
        PDC_time_map = get_PDC_time(K,False)
        # Convert PDC time data to dictionary if it's a DataFrame
        if isinstance(PDC_time_map, pd.DataFrame):
            # Create a dictionary from the DataFrame
            # Assuming the DataFrame has columns for instance name and time
            PDC_time_dict = {}
            for index, row in PDC_time_map.iterrows():
                # Assuming the first column is the instance name and second is the time
                instance_name = row.iloc[0]
                time_value = row.iloc[1]
                timeout_flag = row.iloc[2]
                # if timeout_flag:
                #     time_value /= 2.0
                PDC_time_dict[instance_name] = time_value
            PDC_time_map = PDC_time_dict
        
        # If PDC_time_map is None, initialize an empty dictionary
        if PDC_time_map is None:
            PDC_time_map = {}
            print("No PDC time data found, initializing empty dictionary")
        print(PDC_time_map)
        rewritten_PDC_time_map = defaultdict(float)
        for key, value in PDC_time_map.items():
            new_key = key.split('.')[0]
            rewritten_PDC_time_map[new_key] += value
        print(f"PDC time map size: {len(rewritten_PDC_time_map)}")
        print(rewritten_PDC_time_map)
        ComputeCorrelation(rewritten_PDC_time_map, rewritten_cadical_map, NameRight="PDC Time", NameLeft="Solving Time")
        exit()
    
    if args.CheckInterpolantCNFSizeCorrelation:
        print("-" * 100)
        print(f"Checking Interpolant CNF size correlation for K={K}")
        cnf_sizes = compute_cnf_size_for_category(formula_category,K,args.UseCNFCache or use_cache)
        print(f"CNF sizes: {len(cnf_sizes)}")
        print(f"Average CNF size: {sum(cnf_sizes.values()) / len(cnf_sizes)}")
        interpolant_sizes_for_category = {}
        cnf_sizes_for_correlation = []
        proofdoor_size_map_for_category = {}
        
        # print(f"Interpolant sizes: {(interpolant_size_map)}")
        # print(f"CNF sizes: {(cnf_sizes)}")
        for key, value in interpolant_size_map.items():
            if value[0] < 0:
                continue
            base_name = key.split('.')[0]
            if base_name in cnf_sizes:
                if base_name not in proofdoor_size_map_for_category.keys():
                    proofdoor_size_map_for_category[base_name] = []
                # print(f"{key} {value[0]} {cnf_sizes[base_name]}")
                interpolant_sizes_for_category[key] = value[0]
                cnf_sizes_for_correlation.append(cnf_sizes[base_name])  
                proofdoor_size_map_for_category[base_name].append(value[0])
        # interpolant_sizes_for_category = list(interpolant_sizes_for_category.values())
        interpolant_sizes_for_category_list = []
        for key, value in interpolant_sizes_for_category.items():
            interpolant_sizes_for_category_list.append(value)
        cnf_sizes_for_correlation = np.array(cnf_sizes_for_correlation)
        interpolant_sizes_for_category_list = np.array(interpolant_sizes_for_category_list   )
        correlation, p_value = pearsonr(interpolant_sizes_for_category_list, cnf_sizes_for_correlation)
        print(f"Correlation between interpolant size and cnf size: {correlation}")
        print(f"P-value: {p_value}")
        print(f"total cnf number: {len(cnf_sizes)}")
        print(f"total interpolant number: {len(interpolant_sizes_for_category)}")
        print(f"total proofdoor number: {len(proofdoor_size_map_for_category)}")    
        for key in interpolant_sizes_for_category.keys():
            base_name = key.split('.')[0]
            print(f"{base_name} {interpolant_sizes_for_category[key]} {cnf_sizes[base_name]}")
        # correlation of average size of interpolants in a proofdoor to cnf size
        average_interpolant_size_for_category = {}
        cnf_sizes_for_correlation = []
        for key, value in proofdoor_size_map_for_category.items():
            if len(value) == 0:
                continue
            average_interpolant_size_for_category[key] = (sum(value) / len(value), cnf_sizes[key])
            # cnf_sizes_for_correlation.append(cnf_sizes[key])
        average_interpolant_size_for_category_list = []
        cnf_sizes_for_correlation_list = []
        for key, value in average_interpolant_size_for_category.items():
            average_interpolant_size_for_category_list.append(value[0])
            cnf_sizes_for_correlation_list.append(value[1]  )
        average_interpolant_size_for_category_list = np.array(average_interpolant_size_for_category_list)
        cnf_sizes_for_correlation_list = np.array(cnf_sizes_for_correlation_list)
        correlation, p_value = pearsonr(average_interpolant_size_for_category_list, cnf_sizes_for_correlation_list)
        # check if the data used for pearsonr are correctly matched according to basename
        
        print(f"Correlation between average interpolant size and cnf size: {correlation}")
        print(f"P-value: {p_value}")
        # print(average_interpolant_size_for_category)
        # print(cnf_sizes_for_correlation)
        # print(cnf_sizes)
        # print(interpolant_size_map)
        print("-" * 100)
        
        # exit()
        
        
    if check_cnf_vs_interpolant_size_ratio:
        print("-" * 100)
        print(f"Checking CNF vs Interpolant Size Ratio for K={K}")
        cnf_path = f"ProofDoorBenchmark/{formula_category}/{K}/"
        cnf_sizes = {}
        if (use_cache or args.UseCNFCache) and os.path.exists(f'{cnf_path}/cnfs_sizes.json'):
            cnf_sizes = json.load(open(f'{cnf_path}/cnfs_sizes.json', 'r'))
        else:
            for file in os.listdir(cnf_path):
                if file.endswith('.cnf'):
                    cnf_sizes[file] = os.path.getsize(os.path.join(cnf_path, file))
            json.dump(cnf_sizes, open(f'{cnf_path}/cnfs_sizes.json', 'w'))
        print(f"CNF sizes: {len(cnf_sizes)}")
        print(f"Average CNF size: {sum(cnf_sizes.values()) / len(cnf_sizes)}")
        rewritten_cnf_map = {}
        for key, value in cnf_sizes.items():
            key_parts = key.split('.')
            new_key = key_parts[0]
            rewritten_cnf_map[new_key] = value
        print(f"Rewritten cnf map: {len(rewritten_cnf_map)}")
        ratio = ComputeCNFvsInterpolantSizeRatio(rewritten_cnf_map, proof_door_size_map)
        print(f"CNF vs Interpolant Size Ratio: {ratio}")
        print(f"Average ratio: {sum(ratio) / len(ratio)}")
        print("-" * 100)
        
        
    print(f"Rewritten cadical map: {len(rewritten_cadical_map)}")
    # print(rewritten_cadical_map)
    print(f"Rewritten interpolants map: {len(proof_door_size_map)}")
    print(proof_door_size_map)
    ComputeCorrelation(rewritten_cadical_map, proof_door_size_map)
    print(f"Par2 score: {cadical_par2}")
    