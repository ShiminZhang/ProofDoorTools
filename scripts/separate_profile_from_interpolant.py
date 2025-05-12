import sys

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 separate_profile_from_interpolant.py <interpolant_file>")
        sys.exit(1)
    
    interpolant_file = sys.argv[1]
    with open(interpolant_file, "r") as f:
        lines = f.readlines()
    
    # read from a reversed order
    profile_lines = []
    # Create a new file to store the interpolant without profile information
    interpolant_lines = []
    
    # First pass to identify where profile information starts and ends
    profile_start_index = -1
    
    for line in reversed(lines):
        if line.startswith("TOTAL..."):
            profile_start_index = lines.index(line)
        else:
            if line.startswith("(check-sat)") or "(" in line:
                break
            
    # If profile information was found, extract only the non-profile parts
    if profile_start_index != -1:
        profile_lines = lines[profile_start_index:]
        # Keep everything before the profile section
        interpolant_lines = lines[:profile_start_index]
        with open(interpolant_file + ".profile", "w") as f:
            for line in profile_lines:
                f.write(line)
        with open(interpolant_file, "w") as f:
            for line in interpolant_lines:
                f.write(line)
            
    

if __name__ == "__main__":
    main()