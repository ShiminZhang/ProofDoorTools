from z3 import AstVector, parse_smt2_string
import re

def wrap_with_declarations_and_assert(content : str) -> str:
    if not content.strip().startswith('(declare-') and not content.strip().startswith('(assert'):
        
        # Extract all variable names (starting with 'v' followed by digits)
        variables = set(re.findall(r'\bv\d+\b', content))
        
        # Build declarations
        declarations = '\n'.join(f'(declare-const {var} Bool)' for var in sorted(variables))
        
        # Wrap the content with assert
        content = f"{declarations}\n(assert {content.strip()})\n"
    return content

def parse_interpolant(file_path : str) -> AstVector:
    with open(file_path, 'r') as f:
        content = f.read()
    # check if content is empty
    if not content:
        raise ValueError(f"Interpolant file {file_path} is empty")
    # remove unsat keyword
    content = content.replace("unsat", "")
    content = content.strip()
    content = content.replace("(interpolants", "")
    #remove only one last ) keyword
    content = content.rsplit(")", 1)[0]
    content = wrap_with_declarations_and_assert(content)
    return parse_smt2_string(content)

if __name__ == "__main__":
    file_path = "ProofDoorBenchmark/interpolants_def1/5/6s38.5.0.interpolant"
    interpolant = parse_interpolant(file_path)
    print(interpolant)