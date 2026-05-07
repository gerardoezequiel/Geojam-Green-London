from __future__ import annotations

import argparse
import pickle
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import r2_score
from sklearn.model_selection import KFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from pipeline.src.features import FEATURE_COLUMNS, TARGET_COLUMN, build_feature_frame
from pipeline.src.io import read_msoa, write_parquet


NUMERIC_FEATURES = [
    "log_pop_density",
    "dist_centre_sq",
    "density_x_dist",
    "park_access",
    "is_inner",
]
CATEGORICAL_FEATURES = ["borough"]


@dataclass(frozen=True)
class ModelResult:
    predictions: pd.DataFrame
    cv_mean_r2: float
    feature_importances: pd.DataFrame
    runtime_s: float


def _validate_features(frame: pd.DataFrame) -> None:
    required = ["MSOA21CD", TARGET_COLUMN] + FEATURE_COLUMNS
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f"Feature frame missing required columns: {missing}")
    if frame.empty:
        raise ValueError("Feature frame is empty")


def make_pipeline() -> Pipeline:
    numeric = Pipeline([("imputer", SimpleImputer(strategy="median"))])
    categorical = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    pre = ColumnTransformer(
        [
            ("num", numeric, NUMERIC_FEATURES),
            ("cat", categorical, CATEGORICAL_FEATURES),
        ]
    )
    model = RandomForestRegressor(
        n_estimators=300,
        min_samples_leaf=4,
        n_jobs=-1,
        random_state=42,
    )
    return Pipeline([("preprocess", pre), ("model", model)])


def _importance_table(pipe: Pipeline) -> pd.DataFrame:
    pre = pipe.named_steps["preprocess"]
    names = list(pre.get_feature_names_out())
    names = [n.replace("num__", "").replace("cat__", "") for n in names]
    values = pipe.named_steps["model"].feature_importances_
    table = pd.DataFrame({"feature": names, "importance": values})
    table["base_feature"] = table["feature"]
    table.loc[table["feature"].str.startswith("borough_"), "base_feature"] = "borough"
    grouped = table.groupby("base_feature", as_index=False)["importance"].sum()
    return grouped.sort_values("importance", ascending=False).reset_index(drop=True)


def train_predict(
    feature_frame: pd.DataFrame,
    model_path: str | Path = "assets/models/london/random_forest.pkl",
) -> ModelResult:
    started = time.perf_counter()
    frame = feature_frame.copy()
    _validate_features(frame)
    train = frame.dropna(subset=[TARGET_COLUMN]).reset_index(drop=True)
    if len(train) < 5:
        raise ValueError("At least 5 labelled rows are required for 5-fold CV")
    X = train[FEATURE_COLUMNS]
    y = train[TARGET_COLUMN].astype("float64")
    pipe = make_pipeline()
    cv = KFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(pipe, X, y, cv=cv, scoring="r2", n_jobs=None)
    pipe.fit(X, y)
    pred = pipe.predict(frame[FEATURE_COLUMNS])
    actual = pd.to_numeric(frame[TARGET_COLUMN], errors="coerce")
    residual = actual - pred
    std = residual.dropna().std(ddof=0)
    if not np.isfinite(std) or std == 0:
        std = 1.0
    out = pd.DataFrame(
        {
            "MSOA21CD": frame["MSOA21CD"].astype("string"),
            "predicted_ndvi": pred.astype("float64"),
            "actual_ndvi": actual.astype("float64"),
            "residual": residual.astype("float64"),
            "residual_z": (residual / std).astype("float64"),
        }
    )
    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    with model_path.open("wb") as handle:
        pickle.dump(pipe, handle)
    return ModelResult(out, float(scores.mean()), _importance_table(pipe), time.perf_counter() - started)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--model-output", type=Path, default=Path("assets/models/london/random_forest.pkl"))
    parser.add_argument("--output", type=Path, default=Path("assets/parquet/london/model_predictions.parquet"))
    parser.add_argument("--hierarchical", action="store_true")
    args = parser.parse_args()
    if args.hierarchical:
        print("Hierarchical model skipped: disabled for the 5 minute CI runtime budget.")
    features = build_feature_frame(read_msoa(args.input))
    result = train_predict(features, args.model_output)
    write_parquet(result.predictions, args.output)
    print(f"CV mean R^2: {result.cv_mean_r2:.6f}")
    print(result.feature_importances.head(5).to_string(index=False))
    print(f"Wrote {len(result.predictions)} predictions to {args.output}")


if __name__ == "__main__":
    main()
