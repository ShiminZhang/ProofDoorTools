import os
import sys

def check_if_interpolant_in_cnf_form(interpolant_path):
    with open(interpolant_path, "r") as f:
        lines = f.readlines()
    and_count = 0
    for line in lines:
        if "!" in line:
            return False

        if "and" in line:
            and_count += 1
            if and_count > 1:
                return False
                
    return True

def main():
    interpolant_dir = "ProofDoorBenchmark/interpolants/10/"
    skip_names = []
    # focus_prefixes = ["beem", "oski15", "oc085"]
    good_names = []
    for file in sorted(os.listdir(interpolant_dir)):
        name = file.split(".")[0]
        good_names.append(name)
        # if not any(name.startswith(prefix) for prefix in focus_prefixes):
        #     continue
        if name in skip_names:
            continue
        if file.endswith(".interpolant"):
            interpolant_path = os.path.join(interpolant_dir, file)
            if check_if_interpolant_in_cnf_form(interpolant_path):
                # print(interpolant_path)
                continue
            else:
                skip_names.append(name)
                good_names.remove(name)

    print(good_names)
    # for name in good_names:
    #     print(name)

if __name__ == "__main__":
    main()