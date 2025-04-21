import sys
from z3 import *

def read_smt2_file(filename):
    # Parse SMT2 file
    solver = Solver()
    formulas = parse_smt2_file(filename)
    # The parse_smt2_file function doesn't directly return declarations
    # We need to parse the file separately to get declarations
    
    # Read the file content
    with open(filename, 'r') as file:
        content = file.read()
    
    # Extract declarations using string parsing
    declarations = []
    for line in content.split('\n'):
        if line.startswith('(declare-const'):
            # Extract variable name from declaration
            declarations.append(line)
    
    print(f"Found {len(declarations)} variable declarations")
    asserts = []
    for f in formulas:
        if is_and(f):
            asserts.append(f)
    assert1 = asserts[0]
    assert2 = asserts[1]

    # if len(asserts) != 2:
    #     print("Error: SMT2 file must contain exactly 2 asserts")
    #     sys.exit(1)
        
    return assert1, assert2, declarations

def read_interpolant(filename, definitions):
    # Skip first line of interpolant file
    with open(filename) as f:
        next(f)  # Skip first line
        interpolant_str = f.read()
    # Check if the interpolant string starts with "(interpolants" and replace it with "(assert"
    if interpolant_str.startswith("(interpolants"):
        interpolant_str = "(assert" + interpolant_str[13:]
    # print(interpolant_str[0:-2])
    # Remove the last ")" from the interpolant string
    # if interpolant_str.endswith(")"):
    # interpolant_str = interpolant_str[:-2]
    # print(interpolant_str)
    # Parse as SMT2 formula    
    input = ""
    for d in definitions:
        input += d + "\n"
    input += interpolant_str
    print(input)
    # print(parse_smt2_string(input))
    formula = parse_smt2_string(input)[0]
    print(formula)
    return formula

def check_implication(a, b):
    s = Solver()
    s.add(And(a, Not(b)))
    return s.check() == unsat

def check_implication_not(a, b):
    s = Solver()
    s.add(And(a, b))
    return s.check() == unsat

def main():
    if len(sys.argv) != 3:
        print("Usage: python interpolant_sanity_check.py <smt2_file> <interpolant_file>")
        sys.exit(1)
        
    smt2_file = sys.argv[1]
    interpolant_file = sys.argv[2]
    
    # Read files
    assert1, assert2, definitions = read_smt2_file(smt2_file)
    interpolant = read_interpolant(interpolant_file, definitions)
    
    # Check implications
    implies1 = check_implication(assert1, interpolant)
    implies2 = check_implication_not(interpolant, assert2)
    
    print(f"Assert 1 implies Interpolant: {implies1}")
    print(f"Interpolant implies Assert 2: {implies2}")
    
    if implies1 and implies2:
        print("Interpolant is valid!")
        sys.exit(0)
    else:
        print("Interpolant is invalid!")
        sys.exit(1)
        
if __name__ == "__main__":
    main()
