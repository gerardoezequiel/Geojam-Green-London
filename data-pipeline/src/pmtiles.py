"""GeoPackage to PMTiles via tippecanoe.

Bakes the default variable into the tiles so the SPA's first paint can render
the choropleth without waiting on a parquet fetch (PERFORMANCE.md §4 commit #3).
The full attribute set lives in the parquet sibling; only a small subset is
embedded in the tiles.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import geopandas as gpd


# Subset baked into PMTiles. Everything else stays in the parquet.
DEFAULT_BAKED_FIELDS = (
    "MSOA21CD",
    "MSOA21NM",
    "borough",
    "mean_ndvi_late",
    "mean_delta_ndvi",
)

DROP_MSOA21NM_PREFIXES = ("Brentwood",)


def borough_from_msoa_name(name: str) -> str:
    return re.sub(r"\s*\d+[A-Z]?$", "", name).strip()


def gpkg_to_pmtiles(
    gpkg_path: Path,
    out_path: Path,
    layer_name: str,
    min_zoom: int,
    max_zoom: int,
    fields: tuple[str, ...] = DEFAULT_BAKED_FIELDS,
) -> None:
    if shutil.which("tippecanoe") is None:
        raise SystemExit("tippecanoe not found on PATH (brew install tippecanoe)")

    gdf = gpd.read_file(gpkg_path).to_crs("EPSG:4326")

    before = len(gdf)
    gdf = gdf[~gdf["MSOA21NM"].str.startswith(DROP_MSOA21NM_PREFIXES)].copy()
    gdf = gdf.dropna(subset=["mean_ndvi_late"])
    print(f"  dropped {before - len(gdf)} rows; kept {len(gdf)}")

    if "borough" not in gdf.columns:
        gdf["borough"] = gdf["MSOA21NM"].map(borough_from_msoa_name)

    keep = [c for c in fields if c in gdf.columns] + ["geometry"]
    gdf = gdf[keep]

    out_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        geojson_path = Path(tmp) / "input.geojson"
        gdf.to_file(geojson_path, driver="GeoJSON")

        cmd = [
            "tippecanoe",
            "-o", str(out_path),
            "--force",
            f"--minimum-zoom={min_zoom}",
            f"--maximum-zoom={max_zoom}",
            "--coalesce-densest-as-needed",
            "--extend-zooms-if-still-dropping",
            "--simplification=10",
            "--detect-shared-borders",
            f"--layer={layer_name}",
            f"--name=Green Cities {layer_name}",
            str(geojson_path),
        ]
        print("  $ " + " ".join(cmd))
        subprocess.run(cmd, check=True)

    size_mb = out_path.stat().st_size / 1e6
    print(f"  wrote {out_path}  size_mb={size_mb:.3f}")


def main() -> None:
    p = argparse.ArgumentParser(description="GPKG to PMTiles via tippecanoe")
    p.add_argument("--in", dest="in_path", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--layer", default="msoa")
    p.add_argument("--min-zoom", type=int, default=8)
    p.add_argument("--max-zoom", type=int, default=14)
    args = p.parse_args()

    gpkg_to_pmtiles(args.in_path, args.out, args.layer, args.min_zoom, args.max_zoom)


if __name__ == "__main__":
    main()
