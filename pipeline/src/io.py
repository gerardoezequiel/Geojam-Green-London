from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_CANDIDATES = (
    REPO_ROOT / "geojam_data" / "msoa_full.gpkg",
    REPO_ROOT.parents[1] / "geojam_data" / "msoa_full.gpkg",
)


def default_data_path() -> Path:
    for path in DATA_CANDIDATES:
        if path.exists():
            return path
    checked = ", ".join(str(p) for p in DATA_CANDIDATES)
    raise FileNotFoundError(f"Could not find msoa_full.gpkg. Checked: {checked}")


def read_msoa(path: str | Path | None = None) -> gpd.GeoDataFrame:
    source = Path(path) if path else default_data_path()
    if not source.exists():
        raise FileNotFoundError(f"MSOA source does not exist: {source}")
    gdf = gpd.read_file(source)
    if not isinstance(gdf, gpd.GeoDataFrame):
        raise TypeError("Expected a GeoDataFrame from the MSOA source")
    return gdf


def write_parquet(df: pd.DataFrame, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out

