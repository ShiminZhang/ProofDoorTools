import argparse
import os
from tqdm import tqdm
from utils.paths import get_interpolant_dir,get_branching_order_dir,get_branching_order_log_dir
from utils.utils import group_files_by_basename
from utils.utils import get_python_activate_command

def extract_branching_order_from_interpolants(interpolant_file):
    with open(interpolant_file, 'r') as f:
        lines = f.readlines()

    branching_order = []
    for line in lines:
        literals_in_interpolant = []
        line = line.strip()
        line = line.replace('(', '').replace(')', '')
        line = line.replace('interpolants', '')
        line = line.replace('and', '')
        line = line.replace('or', '')
        line = line.replace('not', '')
        line = line.replace('unsat', '')
        literals = line.split(' ')
        for literal in literals:
            if literal.startswith('v'):
                literals_in_interpolant.append(literal.split('v')[1])
        branching_order.append(literals_in_interpolant)
        
    return branching_order

def save_literals_to_file(literals_in_interpolant, file_name):
    print(f"Writing literals to {file_name}")
    set_of_literals = set()
    with open(file_name, 'w') as f:
        for literals_in_line in literals_in_interpolant:
            for literal in literals_in_line:
                if literal not in set_of_literals:
                    set_of_literals.add(literal)
                    f.write(str(literal) + ' ')
    return set_of_literals

def write_branching_order_to_file(literal_sets, file_name):
    print(f"Writing branching order to {file_name}")
    written_literals = set()
    with open(file_name, 'w') as f:
        for literal_set in literal_sets:
            if len(literal_set) > 0:
                for literal in literal_set:
                    if literal not in written_literals:
                        f.write(str(literal) + ' ')
                        written_literals.add(literal)
                f.write('\n')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--interpolant', type=str, required=False)
    parser.add_argument('--K', type=int, required=True)
    parser.add_argument('--extract_dir', action='store_true', default=False)
    parser.add_argument('--extract_dir_parallel', action='store_true', default=False)
    parser.add_argument('--use_cache', action='store_true', default=False)
    parser.add_argument('--use_cache_only', action='store_true', default=False)
    parser.add_argument('--force_name', type=str, required=False)
    args = parser.parse_args()
    # skip_names = ["6s277rb292","6s210b037","139443p5","6s355rb08740"]
    skip_names = []
    
    if args.interpolant:
        literals_in_interpolant = extract_branching_order_from_interpolants(args.interpolant)
        save_literals_to_file(
            literals_in_interpolant,
            os.path.join(
                get_branching_order_dir(args.K),
                args.interpolant.split('/')[-1].replace('.interpolant','.literals')))
    elif args.extract_dir_parallel:
        dir = get_interpolant_dir(args.K)
        for file in tqdm(os.listdir(dir)):
            # if file.split('.')[0] not in skip_names: #skip the files that are already extracted
            if file.split('.')[0] in skip_names:
                continue
            if file.endswith('.interpolant'):
                target_file = os.path.join(
                        get_branching_order_dir(args.K),
                        file.replace('.interpolant','.literals'))
                activate_python_command = get_python_activate_command()
                log_file = os.path.join(get_branching_order_log_dir(), f"extract_branching_order_{file}.log")
                wrapped = f"{activate_python_command} && python ./scripts/extract_branching_order_from_interpolants.py --interpolant {target_file} --K {args.K}"
                os.system(f"sbatch --time=00:60:00 --output={log_file} --mem=10G --wrap=\"{wrapped}\"")
    elif args.extract_dir:
        force_name=args.force_name
        dir = get_interpolant_dir(args.K)
        for file in tqdm(os.listdir(dir)):
            if file.split('.')[0] in skip_names:
                continue
            if force_name and file.split('.')[0] != force_name:
                continue
            if file.endswith('.interpolant'):
                target_file = os.path.join(
                        get_branching_order_dir(args.K),
                        file.replace('.interpolant','.literals'))
                if os.path.exists(target_file) and os.path.getsize(target_file) > 0 and (args.use_cache or args.use_cache_only):
                    continue
                if args.use_cache_only:
                    continue
                literals_in_interpolant = extract_branching_order_from_interpolants(os.path.join(dir, file))
                save_literals_to_file(
                    literals_in_interpolant,
                    target_file)
        file_groups = group_files_by_basename(
            get_branching_order_dir(args.K),
            args.K,
            limit=args.K,
            force_name=force_name,
            file_extension='.literals')
        print(file_groups)
        for basename, files in file_groups.items():
            if basename in skip_names:
                continue
            print(basename)
            print(files)
            literal_sets = []
            for file in files:
                literal_set = set()
                with open(file, 'r') as f:
                    for line in f:
                        for literal in line.split(' '):
                            literal_set.add(literal)
                literal_sets.append(literal_set)
            write_branching_order_to_file(literal_sets, os.path.join(get_branching_order_dir(args.K), basename + '.branching_order'))
            print("--------------------------------")

if __name__ == '__main__':
    main()