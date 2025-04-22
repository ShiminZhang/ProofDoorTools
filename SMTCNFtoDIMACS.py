# [Not(v288),
#  v3903,
#  Not(v3393),
#  Not(v291),
#  v803,
#  Not(v293),
#  Not(v292),
#  v604,
#  v1375,
#  v1288,
#  v741,
#  v3373,
#  Not(v3380),
#  v637,
#  v3900,
#  Not(v3590),
#  v804,
#  v3339,
#  Not(v3354),
#  v719]

import os
import sys
import re

def parse_cnf_list(input_file):
    """Parse a CNF list from a file or string."""
    print("Parsing CNF list from file:", input_file)
    if os.path.isfile(input_file):
        with open(input_file, 'r') as f:
            content = f.read()
    else:
        content = input_file
    
    # Extract the list content
    match = re.search(r'\[(.*?)\]', content, re.DOTALL)
    if not match:
        raise ValueError("No valid CNF list found in the input")
    
    cnf_text = match.group(1)
    
    # Parse the list items
    clauses = []
    for line in cnf_text.split(','):
        line = line.strip()
        if not line:
            continue
        
        if line.startswith('Not('):
            # Handle negated variables
            var = line[4:-1].strip()  # Extract variable name from Not(var)
            clauses.append(f"-{var}")
        else:
            # Handle positive variables
            clauses.append(line)
    
    return clauses

def convert_to_dimacs(clauses):
    """Convert parsed clauses to DIMACS CNF format."""
    # Create a mapping of variable names to integers
    var_map = {}
    var_counter = 1
    
    dimacs_clauses = []
    for clause in clauses:
        dimacs_clause = []
        is_negated = clause.startswith('-')
        
        if is_negated:
            var_name = clause[1:]
        else:
            var_name = clause
        
        if var_name not in var_map:
            var_map[var_name] = var_counter
            var_counter += 1
        
        var_id = var_map[var_name]
        if is_negated:
            dimacs_clause.append(f"-{var_id}")
        else:
            dimacs_clause.append(f"{var_id}")
        
        dimacs_clauses.append(" ".join(dimacs_clause) + " 0")
    
    # Create the DIMACS header
    header = f"p cnf {len(var_map)} {len(dimacs_clauses)}"
    
    # Create a variable mapping comment section
    var_mapping = [f"c {var_id} = {var_name}" for var_name, var_id in var_map.items()]
    
    return header, var_mapping, dimacs_clauses

def write_dimacs_file(input_file, output_file=None):
    """Process a CNF file and write to DIMACS format."""
    if output_file is None:
        output_file = input_file + ".dimacs"
    
    clauses = parse_cnf_list(input_file)
    header, var_mapping, dimacs_clauses = convert_to_dimacs(clauses)
    
    with open(output_file, 'w') as f:
        f.write(header + "\n")
        for mapping in var_mapping:
            f.write(mapping + "\n")
        for clause in dimacs_clauses:
            f.write(clause + "\n")
    
    print(f"Converted {input_file} to DIMACS format in {output_file}")
    return output_file

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python SMTCNFtoDIMACS.py <input_file> [output_file]")
        sys.exit(1)
    # Process directory of CNF files with K value
    if len(sys.argv) >= 3 and os.path.isdir(sys.argv[1]):
        k_value = int(sys.argv[2])
        directory = sys.argv[1]
        
        # Group files by basename
        file_groups = {}
        for filename in os.listdir(directory):
            if filename.endswith('.cnf'):
                # Extract basename from filename.K.j.smt2.cnf format
                parts = filename.split('.')
                if len(parts) >= 4 and parts[1].isdigit() and int(parts[1]) == k_value:
                    basename = parts[0]
                    if basename not in file_groups:
                        file_groups[basename] = []
                    file_groups[basename].append(os.path.join(directory, filename))
        
        dimacs_files = []
        # Process each group of files
        for basename, files in file_groups.items():
            # Sort files by j value to ensure correct order
            files.sort(key=lambda f: int(f.split('.')[-3]))
            
            # Check if all files in the group have less than 200 lines
            valid_group = True
            for file_path in files:
                with open(file_path, 'r') as f:
                    line_count = sum(1 for _ in f)
                    if line_count >= 200:
                        valid_group = False
                        print(f"Skipping group {basename} as {file_path} has {line_count} lines (>= 200)")
                        break
            
            if not valid_group:
                continue
            
            print(f"Processing group {basename} with files:")
            print(files)
            # Combine all clauses from files with the same basename
            all_clauses = []
            for file_path in files:
                clauses = parse_cnf_list(file_path)
                all_clauses.extend(clauses)
            
            # Convert combined clauses to DIMACS
            header, var_mapping, dimacs_clauses = convert_to_dimacs(all_clauses)
            
            # Write combined DIMACS file
            output_file = f"ProofDoorBenchmark/interpolant_as_cnfs/dimacs/{basename}.{k_value}.dimacs"
            dimacs_files.append(output_file)
            with open(output_file, 'w') as f:
                f.write(header + "\n")
                for mapping in var_mapping:
                    f.write(mapping + "\n")
                for clause in dimacs_clauses:
                    f.write(clause + "\n")
            
            print(f"Combined {len(files)} files for {basename} into {output_file}")
        for file in dimacs_files:
            basename = os.path.basename(file)
            basename = basename.split('.')[0]
            original_cnf_path = f"ProofDoorBenchmark/cnfs/{k_value}/"
            original_cnf = f"{original_cnf_path}{basename}.{k_value}.cnf"
            # Combine original CNF with DIMACS output
            if os.path.exists(original_cnf):
                combined_output = f"./ProofDoorBenchmark/interpolant_as_cnfs/dimacs/{basename}.{k_value}.combined.cnf"
                
                # Read the DIMACS file content and remove comments
                dimacs_clauses = []
                dimacs_header = ""
                dimacs_var_count = 0
                dimacs_clause_count = 0
                
                with open(file, 'r') as dimacs_f:
                    for line in dimacs_f:
                        line = line.strip()
                        if line.startswith('c'):
                            continue
                        elif line.startswith('p'):
                            parts = line.split()
                            dimacs_var_count = int(parts[2])
                            dimacs_clause_count = int(parts[3])
                        elif line:
                            dimacs_clauses.append(line)
                
                # Read the original CNF file content and remove comments
                original_clauses = []
                original_var_count = 0
                original_clause_count = 0
                
                with open(original_cnf, 'r') as original_f:
                    for line in original_f:
                        line = line.strip()
                        if line.startswith('c'):
                            continue
                        elif line.startswith('p'):
                            parts = line.split()
                            original_var_count = int(parts[2])
                            original_clause_count = int(parts[3])
                        elif line:
                            original_clauses.append(line)
                
                # Calculate new header
                total_var_count = max(dimacs_var_count, original_var_count)
                total_clause_count = len(dimacs_clauses) + len(original_clauses)
                new_header = f"p cnf {total_var_count} {total_clause_count}"
                
                # Write combined file with DIMACS content first
                with open(combined_output, 'w') as combined_f:
                    combined_f.write(new_header + "\n")
                    for clause in dimacs_clauses:
                        combined_f.write(clause + "\n")
                    for clause in original_clauses:
                        combined_f.write(clause + "\n")
                
                print(f"Combined {file} and {original_cnf} into {combined_output}")
            else:
                print(f"Original CNF file {original_cnf} not found, skipping combination")

        sys.exit(0)
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    write_dimacs_file(input_file, output_file)
