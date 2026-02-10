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
    content = content.strip()

    # Z3 may output only a status line when no interpolant exists.
    # In particular, for a satisfiable split it prints just "sat".
    first_line = content.splitlines()[0].strip().lower() if content else ""
    if first_line in ("sat", "unknown"):
        raise ValueError(
            f"Interpolant file {file_path} indicates '{first_line}' (no interpolant produced)."
        )

    # remove unsat keyword (usually the first line of Z3 output)
    content = content.replace("unsat", "")
    content = content.strip()
    content = content.replace("(interpolants", "")
    #remove only one last ) keyword
    content = content.rsplit(")", 1)[0]
    content = content.strip()
    if not content:
        raise ValueError(f"Interpolant file {file_path} has no interpolant content after normalization")
    content = wrap_with_declarations_and_assert(content)
    return parse_smt2_string(content)

if __name__ == "__main__":
    file_path = "ProofDoorBenchmark/interpolants_def1/5/6s38.5.0.interpolant"
    interpolant = parse_interpolant(file_path)
    print(interpolant)