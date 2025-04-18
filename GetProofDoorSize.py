import re
# print("Hello")
def count_clauses_in_interpolants(file_path):
    with open(file_path, 'r') as file:
        content = file.read()

    # Find the section with interpolants
    interpolants_section = re.search(r'\(interpolants(.*?)\)', content, re.DOTALL)
    if not interpolants_section:
        print("No interpolants found.")
        return

    # Extract the interpolants content
    interpolants_content = interpolants_section.group(1)

    # Split the interpolants by outer 'and' (each interpolant is wrapped in an 'and')
    interpolants = re.findall(r'\(and(.*?)\)', interpolants_content, re.DOTALL)
    print(len(interpolants))

    # Count clauses in each interpolant
    for i, interpolant in enumerate(interpolants, start=1):
        # Count the number of clauses by counting the number of top-level expressions
        # We assume each clause is separated by a space and starts with a '('
        clauses = re.findall(r'\([^()]*\)', interpolant)
        print(f"Interpolant {i} has {len(clauses)} clauses.")

# Example usage
count_clauses_in_interpolants('test/6s4.10.interpolant')