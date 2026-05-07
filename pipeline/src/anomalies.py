from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from pipeline.src.features import build_feature_frame
from pipeline.src.io import read_msoa, write_parquet
from pipeline.src.model import train_predict
from pipeline.src.spatial import spatial_residuals


ANOMALY_COLUMNS = [
    "MSOA21CD",
    "predicted_ndvi",
    "actual_ndvi",
    "residual",
    "residual_z",
    "gi_star",
    "gi_p",
    "lisa_cluster",
    "surprise_score",
]
CLUSTER_BONUS = {
    # Negative residuals mean the MSOA is greyer than expected. LL receives the
    # largest bonus because grey residuals are surrounded by grey residuals too.
    "LL": 0.75,
    "LH": 0.35,
    "HL": 0.15,
    "HH": 0.0,
    "NS": 0.0,
}


def _filtered_geometries(gdf: gpd.GeoDataFrame, features: pd.DataFrame) -> gpd.GeoDataFrame:
    keep = set(features["MSOA21CD"].astype(str))
    out = gdf[gdf["MSOA21CD"].astype(str).isin(keep)].copy()
    out["MSOA21CD"] = out["MSOA21CD"].astype(str)
    return out.set_index("MSOA21CD").loc[list(features["MSOA21CD"].astype(str))].reset_index()


def build_anomalies(gdf: gpd.GeoDataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    start = time.perf_counter()
    features = build_feature_frame(gdf)
    result = train_predict(features)
    spatial_gdf = _filtered_geometries(gdf, features)
    spatial, moran_i = spatial_residuals(spatial_gdf, result.predictions)
    deficit = (-spatial["residual_z"]).clip(lower=0)
    bonus = spatial["lisa_cluster"].map(CLUSTER_BONUS).fillna(0.0)
    spatial["surprise_score"] = (deficit + bonus).astype("float64")
    out = spatial.loc[:, ANOMALY_COLUMNS].copy()
    out["MSOA21CD"] = out["MSOA21CD"].astype("string")
    for col in [c for c in ANOMALY_COLUMNS if c != "MSOA21CD" and c != "lisa_cluster"]:
        out[col] = pd.to_numeric(out[col], errors="raise").astype("float64")
    out["lisa_cluster"] = out["lisa_cluster"].astype("string")
    metrics = {
        "model_name": result.model_name,
        "cv_mean_r2": result.cv_mean_r2,
        "moran_i": moran_i,
        "runtime_s": time.perf_counter() - start,
        "feature_importances": result.feature_importances.to_dict("records"),
        "rows": len(out),
    }
    return out, metrics


def _json_safe(value: object) -> object:
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument(
        "--output", type=Path, default=Path("assets/parquet/london/anomalies.parquet")
    )
    parser.add_argument(
        "--metrics-output", type=Path, default=Path("assets/models/london/metrics.json")
    )
    args = parser.parse_args()
    anomalies, metrics = build_anomalies(read_msoa(args.input))
    write_parquet(anomalies, args.output)
    args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
    args.metrics_output.write_text(json.dumps(_json_safe(metrics), indent=2), encoding="utf-8")
    print(f"CV mean R^2: {metrics['cv_mean_r2']:.6f}")
    print(f"Runtime seconds: {metrics['runtime_s']:.3f}")
    print(f"Wrote {len(anomalies)} anomalies to {args.output}")


if __name__ == "__main__":
    main()
