from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from pipeline.src.features import build_feature_frame
from pipeline.src.io import read_msoa, write_parquet
from pipeline.src.model import train_predict


CLUSTERS = {"HH", "HL", "LH", "LL", "NS"}


def _validate(gdf: gpd.GeoDataFrame, predictions: pd.DataFrame) -> None:
    if "MSOA21CD" not in gdf.columns or "geometry" not in gdf.columns:
        raise ValueError("Spatial input GeoDataFrame needs MSOA21CD and geometry")
    required = ["MSOA21CD", "residual", "residual_z"]
    missing = [c for c in required if c not in predictions.columns]
    if missing:
        raise ValueError(f"Prediction frame missing required columns: {missing}")
    if predictions.empty:
        raise ValueError("Prediction frame is empty")


def _esda_stats(gdf: gpd.GeoDataFrame, values: np.ndarray) -> pd.DataFrame:
    from esda.getisord import G_Local
    from esda.moran import Moran, Moran_Local
    from libpysal.weights import Queen

    weights = Queen.from_dataframe(gdf, ids=gdf["MSOA21CD"].tolist(), use_index=False)
    weights.transform = "r"
    moran = Moran(values, weights)
    local = Moran_Local(values, weights, permutations=99, seed=42)
    gi = G_Local(values, weights, star=True, permutations=99, seed=42)
    cluster = np.repeat("NS", len(values)).astype(object)
    significant = local.p_sim < 0.05
    high = values >= values.mean()
    lag = weights.sparse @ values
    lag_high = lag >= lag.mean()
    cluster[significant & high & lag_high] = "HH"
    cluster[significant & high & ~lag_high] = "HL"
    cluster[significant & ~high & lag_high] = "LH"
    cluster[significant & ~high & ~lag_high] = "LL"
    out = pd.DataFrame(
        {"gi_star": gi.Zs, "gi_p": gi.p_sim, "lisa_cluster": cluster}
    )
    out.attrs["moran_i"] = float(moran.I)
    return out


def _fallback_stats(gdf: gpd.GeoDataFrame, values: np.ndarray) -> pd.DataFrame:
    joined = gdf.sindex.query(gdf.geometry, predicate="intersects")
    neighbours = {i: set() for i in range(len(gdf))}
    for left, right in zip(*joined):
        if left != right and gdf.geometry.iloc[left].touches(gdf.geometry.iloc[right]):
            neighbours[left].add(right)
    z = (values - values.mean()) / (values.std(ddof=0) or 1.0)
    gi_star, clusters = [], []
    for i, val in enumerate(z):
        idx = list(neighbours[i]) + [i]
        local = float(z[idx].mean()) if idx else 0.0
        gi_star.append(local)
        if abs(local) < 1.96:
            clusters.append("NS")
        elif val >= 0 and local >= 0:
            clusters.append("HH")
        elif val >= 0:
            clusters.append("HL")
        elif local >= 0:
            clusters.append("LH")
        else:
            clusters.append("LL")
    out = pd.DataFrame({"gi_star": gi_star, "gi_p": 1.0, "lisa_cluster": clusters})
    out.attrs["moran_i"] = float("nan")
    return out


def spatial_residuals(
    gdf: gpd.GeoDataFrame, predictions: pd.DataFrame
) -> tuple[pd.DataFrame, float]:
    _validate(gdf, predictions)
    merged = gdf[["MSOA21CD", "geometry"]].merge(predictions, on="MSOA21CD", how="inner")
    if len(merged) != len(predictions):
        raise ValueError("Prediction rows do not align with MSOA geometries")
    spatial_gdf = gpd.GeoDataFrame(merged, geometry="geometry", crs=gdf.crs)
    values = spatial_gdf["residual"].astype("float64").to_numpy()
    if not np.isfinite(values).all():
        raise ValueError("Residuals must be finite for spatial statistics")
    try:
        stats = _esda_stats(spatial_gdf, values)
    except ImportError:
        stats = _fallback_stats(spatial_gdf, values)
    out = pd.concat(
        [spatial_gdf.drop(columns="geometry").reset_index(drop=True), stats], axis=1
    )
    if not set(out["lisa_cluster"]).issubset(CLUSTERS):
        raise ValueError("Unexpected LISA cluster values emitted")
    return out, float(stats.attrs.get("moran_i", np.nan))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=Path("assets/parquet/london/spatial.parquet"))
    args = parser.parse_args()
    gdf = read_msoa(args.input)
    features = build_feature_frame(gdf)
    predictions = train_predict(features).predictions
    filtered = gdf[gdf["MSOA21CD"].isin(features["MSOA21CD"])]
    out, moran_i = spatial_residuals(filtered, predictions)
    write_parquet(out, args.output)
    print(f"Global Moran's I: {moran_i:.6f}")
    print(f"Wrote {len(out)} spatial rows to {args.output}")


if __name__ == "__main__":
    main()

