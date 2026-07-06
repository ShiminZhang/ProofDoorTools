import csv
import os
from utils.paths import get_interpolant_cnf_dir

CATEGORY_CSV_PATH = os.path.join(os.path.dirname(__file__), "../../category.csv")

class CategoryData:
    _instance = None
    _initialized = False
    
    def __new__(cls, csv_path=None):
        if cls._instance is None:
            cls._instance = super(CategoryData, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, csv_path=None):
        # Only initialize once, even if __init__ is called multiple times
        if not self._initialized:
            self.linear_instances = []
            self.polynomial_instances = []
            self.exponential_instances = []
            self.valid_instances = []
            self.unknown_instances = []
            self.too_few_data_instances = []
            self.exponential_too_many_data_instances = []
            self.all_instances = []
            self._load(csv_path or CATEGORY_CSV_PATH)
            self._initialized = True

    def _load(self, csv_path):
        try:
            with open(csv_path, newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    name = row['instance_name']
                    category = row['type_of_equation'].strip().lower()
                    self.all_instances.append(name)
                    if category == "linear":
                        self.linear_instances.append(name)
                    elif category == "polynomial":
                        self.polynomial_instances.append(name)
                    elif category == "exponential":
                        self.exponential_instances.append(name)
                    elif category == "too few data":
                        self.too_few_data_instances.append(name)
                    elif category == "exponential( too many data)":
                        self.exponential_too_many_data_instances.append(name)
                    else:
                        self.unknown_instances.append(name)
        except Exception as e:
            print(e)
            # If the file is missing or malformed, leave lists empty
            pass

# Singleton instance - CSV will only be read once
category_data = CategoryData()

# For backward compatibility with existing code - these are now properties
def get_linear_instances():
    return category_data.linear_instances

def get_polynomial_instances():
    return category_data.polynomial_instances

def get_exponential_instances():
    return category_data.exponential_instances

def get_valid_instances():
    return category_data.valid_instances

def get_all_instances():
    return category_data.all_instances

# Module-level variables for backward compatibility - these are now functions
def linear_instances():
    return category_data.linear_instances

def polynomial_instances():
    return category_data.polynomial_instances

def exponential_instances():
    return category_data.exponential_instances

def valid_instances():
    return category_data.valid_instances

def all_instances():
    return category_data.all_instances


def get_category(instance_name):
    if instance_name in linear_instances():
        return "linear"
    elif instance_name in polynomial_instances():
        return "polynomial"
    elif instance_name in exponential_instances():
        return "exponential"
    else:
        return "unknown"
    
def get_instance_list(category):
    if category == "linear":
        return linear_instances()
    elif category == "polynomial":
        return polynomial_instances()
    elif category == "exponential":
        return exponential_instances()
    elif category == "valid":
        return valid_instances()
    elif category == "all":
        return linear_instances() + polynomial_instances() + exponential_instances()
    else:
        return []


def _perm_suffix(permute: str = None, permute_index: int = 0) -> str:
    if not permute:
        return ""
    return f".perm_{permute}_{permute_index}"


def get_category_set_from_dashboard(category: str, csv_path="./dashboard_data.csv") -> set:
    """Return instance names with the requested category in dashboard_data.csv."""
    result = set()
    if not category or not os.path.exists(csv_path):
        return result
    with open(csv_path, "r") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) > 2 and row[2] == category:
                result.add(row[0])
    return result


def _find_def5_complete_smtcnf_instances(
    K: int,
    *,
    reverse: bool = False,
    permute: str = None,
    permute_index: int = 0,
) -> list:
    base_dir = get_interpolant_cnf_dir(K, 5)
    if not os.path.exists(base_dir):
        return []

    smtcnf_suffix = ".reverse.smtcnf" if reverse else ".smtcnf"
    ending = f"{_perm_suffix(permute, permute_index)}{smtcnf_suffix}"
    marker = f".{K}."
    full_set = set(range(K))
    index_map = {}

    for fname in os.listdir(base_dir):
        if not fname.endswith(ending):
            continue
        core = fname[: -len(ending)]
        if marker not in core:
            continue
        instance, idx_str = core.rsplit(marker, 1)
        if not instance or not idx_str:
            continue
        try:
            idx = int(idx_str)
        except ValueError:
            continue
        if idx < 0 or idx >= K:
            continue
        if os.path.getsize(os.path.join(base_dir, fname)) == 0:
            continue
        index_map.setdefault(instance, set()).add(idx)

    return sorted(inst for inst, idxs in index_map.items() if idxs == full_set)


def _find_def5_any_smtcnf_instances(
    K: int,
    *,
    reverse: bool = False,
    permute: str = None,
    permute_index: int = 0,
) -> list:
    base_dir = get_interpolant_cnf_dir(K, 5)
    if not os.path.exists(base_dir):
        return []

    smtcnf_suffix = ".reverse.smtcnf" if reverse else ".smtcnf"
    ending = f"{_perm_suffix(permute, permute_index)}{smtcnf_suffix}"
    marker = f".{K}."
    instances = set()

    for fname in os.listdir(base_dir):
        if not fname.endswith(ending):
            continue
        core = fname[: -len(ending)]
        if marker not in core:
            continue
        instance, idx_str = core.rsplit(marker, 1)
        if instance and idx_str.isdigit():
            instances.add(instance)

    return sorted(instances)


def get_lucky_instances(
    K: int,
    category: str = None,
    *,
    auto_effective_K: bool = False,
    reverse: bool = False,
    permute: str = None,
    permute_index: int = 0,
    dashboard_csv_path: str = "./dashboard_data.csv",
) -> list:
    """
    Return pddef=5 instances eligible for absorption.

    By default this requires all K converted non-empty .smtcnf files under
    interpolant_as_cnfs_5/<K>/. With auto_effective_K, any instance with at
    least one converted file is accepted and the caller can infer effective K.
    """
    if auto_effective_K:
        instances = _find_def5_any_smtcnf_instances(
            K, reverse=reverse, permute=permute, permute_index=permute_index
        )
    else:
        instances = _find_def5_complete_smtcnf_instances(
            K, reverse=reverse, permute=permute, permute_index=permute_index
        )

    if category is not None:
        allowed = get_category_set_from_dashboard(category, dashboard_csv_path)
        instances = [inst for inst in instances if inst in allowed]
    return instances
    
def get_linear_instances():
    return linear_instances()

def get_polynomial_instances():
    return polynomial_instances()

def get_exponential_instances():
    return exponential_instances()

def find_instance_interpolant(in_category, pddef=3):
    print(f"Finding exponential instances in interpolant directory with pddef {pddef}")
    interpolant_dir = f"./ProofDoorBenchmark/interpolants_def{pddef}/10"
    count_map = {}
    k = 10
    for file in os.listdir(interpolant_dir):
        if file.endswith(".interpolant"):
            name = file.split(".")[0]
            category = get_category(name)
            if category == in_category:
                if name in count_map:
                    count_map[name] += 1
                else:
                    count_map[name] = 1
    for name, count in count_map.items():
        if count == k:
            print(f"{name}")

    if len(count_map) == 0:
        print(f"No {in_category} instances found")
        return
    print(count_map)
    for file in os.listdir(interpolant_dir):
        if file.endswith(".interpolant"):
            name = file.split(".")[0]
            if name in count_map:
                print(f"{file}")

def find_instance_absorption_figures(in_category):
    absorption_figures  = "./figures/absorption_experiments/"
    for file in os.listdir(absorption_figures):
        if file.endswith(".pnf"):
            name = file.split(" ")[-1]
            name = name.split(".")[0]
            category = get_category(name)
            if category == in_category:
                print(f"{file}")

def find_combination_formulas(k,pddef,  in_category):
    combined_cnfs = f"./ProofDoorBenchmark/combined_cnfs/pddef_{pddef}/{k}"
    for file in os.listdir(combined_cnfs):
        if file.endswith(".cnf"):
            # name = file.split(".")[0]

            name = file.split(".")[0]
            category = get_category(name)
            if category == in_category:
                print(f"{file}")
# def find_exponential_combination_figures():
#     combination_figures  = "./figures/combine/"
#     for file in os.listdir(combination_figures):
#         if file.endswith(".pnf"):
#             name = file.split(" ")[-1]
#             name = name.split(".")[0]
#             category = get_category(name)
#             if category == "exponential":
#                 print(f"{file}")

def main():
    print(get_instance_list("exponential"))
    # print(get_instance_list("exponential"))
    # find_instance_interpolant("exponential", 3)
    # print("--------------------------------")
    # find_instance_interpolant("exponential", 1)
    # find_instance_interpolant("linear", 3)
    # print("--------------------------------")
    # find_instance_interpolant("linear", 1)
    # print("--------------------------------")
    # find_instance_absorption_figures("exponential")
    # print("--------------------------------")
    # find_instance_absorption_figures("linear")
    # find_combination_formulas(10, 1, "exponential")
    pass

if __name__ == "__main__":
    main()
