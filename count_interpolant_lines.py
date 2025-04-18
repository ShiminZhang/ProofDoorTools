import re
import sys
import os

def process_content(content):
    result = []
    stack = []
    let_count = 0
    i = 0
    while i < len(content):
        if content[i:i+4] == '(let':
            stack.append('let')
            let_count += 1
            # Skip to the next character after 'let'
            i += 4
            continue
        elif content[i] == '(' and stack:
            stack.append('(')
        elif content[i] == ')' and stack:
            stack.pop()
            if not stack:  # If we've closed all brackets
                i += 1
                continue
        if not stack:  # Only add characters that are not within let expressions
            result.append(content[i])
        i += 1
    return ''.join(result), let_count

def count_lines(file_path):
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Remove all let expressions and count them
    content, let_count = process_content(content)
    
    # Split into lines and filter out empty lines
    lines = [line for line in content.split('\n') if line.strip()]
    
    return len(lines), let_count

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python cnf_to_smt2.py <input_file.cnf>")
        sys.exit(1)

    file_path = sys.argv[1]
    if not os.path.isfile(file_path):
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)
    # file_path = "test/6s4.10.interpolant"
    line_count, let_count = count_lines(file_path)
    # print(f"Number of lines (excluding let expressions): {line_count-3}")
    # print(f"Number of let expressions: {let_count}") 
    print(f"size of proofdoor: {line_count+let_count-3}") 
    