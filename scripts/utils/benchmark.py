import argparse
import json
import os
from typing import Dict, List, Optional

from utils.paths import (
    get_benchmark_dir,
    get_CNF_dir,
    get_interpolant_dir,
    get_interpolant_cnf_dir,
)


class InstanceStatus:
    not_started = "not_started"
    interpolant_generated = "interpolant_generated"


class InstanceData:
    def __init__(self, name: str, K: int):
        self.name = name
        self.K = K
        self.status = InstanceStatus.not_started
        self.formula_size: int = 0
        self.proofdoor_size: int = 0
        self.interpolants_paths: Dict[int, List[str]] = {}
        self.interpolant_cnfs_paths: Dict[int, List[str]] = {}

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "K": self.K,
            "status": self.status,
            "formula_size": self.formula_size,
            "proofdoor_size": self.proofdoor_size,
            "interpolants_paths": self.interpolants_paths,
            "interpolant_cnfs_paths": self.interpolant_cnfs_paths,
        }

    @staticmethod
    def from_dict(d: Dict) -> "InstanceData":
        obj = InstanceData(d["name"], d["K"])
        obj.status = d.get("status", InstanceStatus.not_started)
        obj.formula_size = d.get("formula_size", 0)
        obj.proofdoor_size = d.get("proofdoor_size", 0)
        obj.interpolants_paths = d.get("interpolants_paths", {})
        obj.interpolant_cnfs_paths = d.get("interpolant_cnfs_paths", {})
        return obj


class Instance:
    def __init__(self, name: str, K: int, path: Optional[str] = None):
        self.name = name
        self.K = K
        if path is None:
            path = os.path.join(get_benchmark_dir(), f"{name}.{K}.json")
        self.path = path
        self.data: InstanceData = InstanceData(name, K)

    def _compute_formula_size(self) -> int:
        cnf_path = os.path.join(get_CNF_dir(self.K), f"{self.name}.{self.K}.cnf")
        if not os.path.exists(cnf_path) or os.path.getsize(cnf_path) == 0:
            return 0
        clauses = 0
        with open(cnf_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("c") or line.startswith("p "):
                    continue
                if line.endswith(" 0") or line.endswith("\t0") or line == "0":
                    clauses += 1
        return clauses

    def _compute_proofdoor_size_and_paths(self) -> int:
        base_interp = get_interpolant_dir(self.K)
        base_cnf = get_interpolant_cnf_dir(self.K)
        total = 0
        self.data.interpolants_paths = {}
        self.data.interpolant_cnfs_paths = {}
        for i in range(self.K):
            interp_path = os.path.join(
                base_interp, f"{self.name}.{self.K}.{i}.interpolant"
            )
            if os.path.exists(interp_path) and os.path.getsize(interp_path) > 0:
                self.data.interpolants_paths[i] = [interp_path]

            cnf_path = os.path.join(
                base_cnf, f"{self.name}.{self.K}.{i}.smtcnf"
            )
            if os.path.exists(cnf_path) and os.path.getsize(cnf_path) > 0:
                self.data.interpolant_cnfs_paths[i] = [cnf_path]
                with open(cnf_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("c") or line.startswith("p "):
                            continue
                        if line.endswith(" 0") or line.endswith("\t0") or line == "0":
                            total += 1
        return total

    def update_data(self) -> None:
        self.data.formula_size = self._compute_formula_size()
        self.data.proofdoor_size = self._compute_proofdoor_size_and_paths()
        if self.data.proofdoor_size > 0:
            self.data.status = InstanceStatus.interpolant_generated

    def save(self, path: Optional[str] = None) -> None:
        if path is None:
            path = self.path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.data.to_dict(), f)

    def load(self, path: Optional[str] = None) -> None:
        if path is None:
            path = self.path
        if not os.path.exists(path):
            return
        with open(path, "r") as f:
            d = json.load(f)
        self.data = InstanceData.from_dict(d)


def compute_interpolants(instance: Instance) -> None:
    instance.update_data()
    instance.save()


def compute_smtcnfs(instance: Instance) -> None:
    instance.update_data()
    instance.save()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", type=str, required=True)
    parser.add_argument("--K", type=int, required=True)
    parser.add_argument("--update_data", action="store_true", default=False)
    parser.add_argument("--compute_interpolants", action="store_true", default=False)
    parser.add_argument("--compute_smtcnfs", action="store_true", default=False)
    return parser.parse_args()


def main():
    args = parse_args()
    inst = Instance(args.name, args.K)
    if args.compute_interpolants:
        compute_interpolants(inst)
    elif args.compute_smtcnfs:
        compute_smtcnfs(inst)
    elif args.update_data:
        inst.update_data()
        inst.save()
    print(json.dumps(inst.data.to_dict()))


if __name__ == "__main__":
    main()