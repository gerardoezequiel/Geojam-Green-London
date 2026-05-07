from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from pipeline.src.io import read_msoa, write_parquet


ID_COLS = ["MSOA21CD", "MSOA21NM"]
FEATURE_COLUMNS = [
    "log_pop_density",
    "log_area_km2",
    "dist_to_centre_km",
    "dist_to_park_km",
    "dist_centre_sq",
    "density_x_dist",
    "park_access",
    "is_inner",
    "centroid_lon",
    "centroid_lat",
    "borough",
]
TARGET_COLUMN = "mean_ndvi_late"
LONDON_BOROUGHS = {
    "Barking and Dagenham", "Barnet", "Bexley", "Brent", "Bromley", "Camden",
    "City of London", "Croydon", "Ealing", "Enfield", "Greenwich", "Hackney",
    "Hammersmith and Fulham", "Haringey", "Harrow", "Havering", "Hillingdon",
    "Hounslow", "Islington", "Kensington and Chelsea", "Kingston upon Thames",
    "Lambeth", "Lewisham", "Merton", "Newham", "Redbridge",
    "Richmond upon Thames", "Southwark", "Sutton", "Tower Hamlets",
    "Waltham Forest", "Wandsworth", "Westminster",
}
REQUIRED_COLUMNS = [
    "MSOA21CD",
    "MSOA21NM",
    "pop_density",
    "dist_to_centre_km",
    "dist_to_park_km",
    "area_km2",
    TARGET_COLUMN,
]


def validate_msoa(gdf: gpd.GeoDataFrame) -> None:
    if not isinstance(gdf, gpd.GeoDataFrame):
        raise TypeError("features expects a GeoDataFrame")
    missing = [c for c in REQUIRED_COLUMNS if c not in gdf.columns]
    if missing:
        raise ValueError(f"MSOA frame missing required columns: {missing}")
    if gdf.empty:
        raise ValueError("MSOA frame is empty")


def build_feature_frame(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    validate_msoa(gdf)
    base = gdf.loc[:, REQUIRED_COLUMNS].copy()
    numeric = ["pop_density", "dist_to_centre_km", "dist_to_park_km", "area_km2"]
    for col in numeric:
        base[col] = pd.to_numeric(base[col], errors="coerce")
    if (base["area_km2"] <= 0).any():
        raise ValueError("area_km2 must be positive")
    out = pd.DataFrame(index=base.index)
    out["MSOA21CD"] = base["MSOA21CD"].astype("string")
    out["MSOA21NM"] = base["MSOA21NM"].astype("string")
    out[TARGET_COLUMN] = pd.to_numeric(base[TARGET_COLUMN], errors="coerce")
    out["log_pop_density"] = np.log1p(base["pop_density"]).astype("float64")
    out["log_area_km2"] = np.log1p(base["area_km2"]).astype("float64")
    out["dist_to_centre_km"] = base["dist_to_centre_km"].astype("float64")
    out["dist_to_park_km"] = base["dist_to_park_km"].astype("float64")
    out["dist_centre_sq"] = (base["dist_to_centre_km"] ** 2).astype("float64")
    out["density_x_dist"] = (
        base["pop_density"] * base["dist_to_centre_km"]
    ).astype("float64")
    # The notebook defines park access as park distance normalised by MSOA scale.
    out["park_access"] = (
        base["dist_to_park_km"] / np.sqrt(base["area_km2"])
    ).astype("float64")
    out["is_inner"] = (base["dist_to_centre_km"] < 8.0).astype("int64")
    centroid_source = gdf
    if gdf.crs is not None and gdf.crs.is_geographic:
        centroid_source = gdf.to_crs("EPSG:27700")
    centroids = gpd.GeoSeries(centroid_source.geometry.centroid, crs=centroid_source.crs)
    if centroids.crs is not None and not centroids.crs.is_geographic:
        centroids = centroids.to_crs("EPSG:4326")
    out["centroid_lon"] = centroids.x.astype("float64")
    out["centroid_lat"] = centroids.y.astype("float64")
    out["borough"] = base["MSOA21NM"].astype(str).str.rsplit(" ", n=1).str[0]
    out["borough"] = out["borough"].astype("string")
    out = out[out["borough"].isin(LONDON_BOROUGHS)]
    out = out.dropna(subset=[TARGET_COLUMN])
    if out.empty:
        raise ValueError("No London MSOAs with a valid mean_ndvi_late target remain")
    ordered = ID_COLS + [TARGET_COLUMN] + FEATURE_COLUMNS
    return out.loc[:, ordered].reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument(
        "--output", type=Path, default=Path("assets/parquet/london/features.parquet")
    )
    args = parser.parse_args()
    frame = build_feature_frame(read_msoa(args.input))
    write_parquet(frame, args.output)
    print(f"Wrote {len(frame)} feature rows to {args.output}")


if __name__ == "__main__":
    main()
