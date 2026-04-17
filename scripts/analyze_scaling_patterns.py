#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import re
from dataclasses import dataclass
from statistics import mean, median
from typing import Callable, Dict, Iterable, List, Sequence, Tuple
from utils.paths import get_aiger_dir, get_circuit_features_dir
from aigverse import (  # type: ignore[import-not-found]
    DepthAig,
    read_aiger_into_aig,
    read_aiger_into_sequential_aig,
)
import numpy as np  # type: ignore[import-not-found]
from sklearn.ensemble import RandomForestRegressor  # type: ignore[import-not-found]
from sklearn.metrics import mean_absolute_error, r2_score  # type: ignore[import-not-found]
from sklearn.model_selection import train_test_split  # type: ignore[import-not-found]
from utils.data_analysis import extract_aiger_features, DataPoint, load_data_points
from tqdm import tqdm


def random_forest_regression(data_points: List[DataPoint], yfunction: Callable, cache_path: str) -> None:
    if not data_points:
        raise ValueError("random_forest_regression: empty data_points")

    feature_names = [
        "K",
        "formula_size",
        "proofdoor_size",
        "proof_size",
        "nlatches",
        "nands",
        "noutputs",
        "depth",
        "nclauses",
        "ncnfvariables",
    ]

    def _row(p: DataPoint) -> List[float]:
        return [
            float(p.K),
            float(p.formula_size),
            float(p.proofdoor_size),
            float(p.proof_size),
            float(p.nlatches),
            float(p.nands),
            float(p.noutputs),
            float(p.depth),
            float(p.nclauses),
            float(p.ncnfvariables),
        ]

    X = np.asarray([_row(p) for p in data_points], dtype=float)
    y = np.asarray([float(yfunction(p)) for p in data_points], dtype=float)

    # Drop any rows with NaN/inf target or features.
    mask = np.isfinite(y)
    mask &= np.isfinite(X).all(axis=1)
    X = X[mask]
    y = y[mask]
    kept_points = [p for p, ok in zip(data_points, mask) if bool(ok)]

    if len(kept_points) < 8:
        raise ValueError(f"random_forest_regression: not enough usable points ({len(kept_points)})")

    print(f"random_forest_regression: usable_points={len(kept_points)} (after dropping non-finite rows)")

    X_train, X_test, y_train, y_test, pts_train, pts_test = train_test_split(
        X,
        y,
        kept_points,
        test_size=0.2,
        random_state=0,
        shuffle=True,
    )

    model = RandomForestRegressor(
        n_estimators=600,
        random_state=0,
        n_jobs=-1,
        min_samples_leaf=1,
        oob_score=True,
        bootstrap=True,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    metrics = {
        "n_points": int(len(kept_points)),
        "n_train": int(len(pts_train)),
        "n_test": int(len(pts_test)),
        "r2_test": float(r2_score(y_test, y_pred)),
        "mae_test": float(mean_absolute_error(y_test, y_pred)),
        "oob_score": float(getattr(model, "oob_score_", float("nan"))),
    }

    importances = list(zip(feature_names, [float(x) for x in getattr(model, "feature_importances_", [])]))
    importances.sort(key=lambda t: t[1], reverse=True)

    preds = []
    for p, yt, yp in zip(pts_test, y_test.tolist(), y_pred.tolist()):
        preds.append(
            {
                "instance": p.instance,
                "K": int(p.K),
                "y_true": float(yt),
                "y_pred": float(yp),
            }
        )

    payload = {
        "model": "RandomForestRegressor",
        "model_params": {
            "n_estimators": int(getattr(model, "n_estimators", 0)),
            "random_state": 0,
        },
        "features": feature_names,
        "metrics": metrics,
        "feature_importances": [{"feature": f, "importance": imp} for (f, imp) in importances],
        "test_predictions": preds,
    }

    os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)

    print(f"random_forest_regression: n_train={len(pts_train)} n_test={len(pts_test)} r2_test={metrics['r2_test']} mae_test={metrics['mae_test']}")
    for feat, imp in importances:
        print(f"{feat}\t{imp}")

def build_cache_path(method: str, y: str, summary_path: str) -> str:
    return os.path.join(os.path.dirname(summary_path), f"{method}_{y}.json")

def read_instances_from_summary(summary_path: str, K: int) -> List[str]:
    with open(summary_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        return sorted({row["instance_name"] for row in reader if int(row["K"]) == int(K)})

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--K", type=int, default=10)
    parser.add_argument("--method", type=str, default="randomforest")
    parser.add_argument("--y", type=str, default="solvingtime")
    parser.add_argument("--summary_path", type=str, required=True)
    parser.add_argument("--prepare_aiger_features", action="store_true", default=False)
    parser.add_argument("--clear_cache", action="store_true", default=False)

    args = parser.parse_args()

    instances = read_instances_from_summary(args.summary_path, args.K)


    if args.prepare_aiger_features:
        extract_aiger_features()
        exit()

    if args.clear_cache:
        cache_path = build_cache_path(args.method, args.y, args.summary_path)
        if os.path.exists(cache_path):
            os.remove(cache_path)
        
    data_points = load_data_points(args.K, instances)
    if args.method == "randomforest":
        random_forest_regression(data_points, lambda p: p.solving_time, build_cache_path(args.method, args.y, args.summary_path))
    else:
        raise ValueError(f"Unknown method: {args.method}")

if __name__ == "__main__":
    main()
