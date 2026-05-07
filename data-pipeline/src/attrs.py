"""GeoPackage attribute table to a sorted, row-grouped Parquet for DuckDB-Wasm.

Sort + row-group is the highest-leverage perf win (PERFORMANCE.md §4): zone maps
in Parquet metadata let DuckDB skip row groups whose value range falls outside
the predicate, cutting bytes-fetched by 5-10x for typical viewport queries.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import geopandas as gpd
import pyarrow as pa
import pyarrow.parquet as pq


# Drop the one MSOA outside London raster coverage (Brentwood 003) and any
# similar non-London outliers if they ever appear.
DROP_MSOA21NM_PREFIXES = ("Brentwood",)


def borough_from_msoa_name(name: str) -> str:
    """Extract borough name from MSOA21NM, e.g. 'Hackney 023' -> 'Hackney'."""
    return re.sub(r"\s*\d+[A-Z]?$", "", name).strip()


def gpkg_to_parquet(gpkg_path: Path, out_path: Path, drop_geometry: bool = True) -> None:
    gdf = gpd.read_file(gpkg_path).to_crs("EPSG:4326")

    before = len(gdf)
    gdf = gdf[~gdf["MSOA21NM"].str.startswith(DROP_MSOA21NM_PREFIXES)].copy()
    print(f"  dropped {before - len(gdf)} non-London MSOAs; kept {len(gdf)}")

    if "mean_ndvi_late" in gdf.columns:
        gdf = gdf.dropna(subset=["mean_ndvi_late"]).copy()

    gdf["borough"] = gdf["MSOA21NM"].map(borough_from_msoa_name)

    centroids = gdf.geometry.centroid
    gdf["centroid_lon"] = centroids.x
    gdf["centroid_lat"] = centroids.y

    if drop_geometry:
        df = gdf.drop(columns="geometry")
    else:
        df = gdf

    # Sort by borough then MSOA code so range queries on either field benefit
    # from Parquet zone-map pruning.
    df = df.sort_values(["borough", "MSOA21CD"]).reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df, preserve_index=False)

    pq.write_table(
        table,
        out_path,
        compression="zstd",
        compression_level=9,
        row_group_size=200,
        use_dictionary=True,
        write_statistics=True,
    )
    size_mb = out_path.stat().st_size / 1e6
    print(f"  wrote {out_path}  rows={len(df)}  cols={len(df.columns)}  size_mb={size_mb:.3f}")
    print(f"  columns: {list(df.columns)}")


def main() -> None:
    p = argparse.ArgumentParser(description="GPKG attributes to sorted Parquet")
    p.add_argument("--in", dest="in_path", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--keep-geometry", action="store_true")
    args = p.parse_args()

    gpkg_to_parquet(args.in_path, args.out, drop_geometry=not args.keep_geometry)


if __name__ == "__main__":
    main()
