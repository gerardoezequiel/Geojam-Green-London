"""Convert a numpy NDVI raster to a Cloud Optimised GeoTIFF.

The source rasters in geojam_data/ are float32 EPSG:27700 with shape 2355x2856
at 20 m resolution. We reproject to EPSG:3857 (web Mercator) and emit deflate-
compressed COGs with internal overviews so deck.gl-raster + COGSource can
range-fetch them efficiently.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import Affine
from rasterio.warp import Resampling, calculate_default_transform, reproject
from rio_cogeo.cogeo import cog_translate
from rio_cogeo.profiles import cog_profiles


NODATA_FLOAT = -9999.0


def load_array(path: Path) -> np.ndarray:
    return np.load(path).astype("float32")


def _src_profile(arr: np.ndarray, meta: dict) -> dict:
    height, width = arr.shape
    transform = Affine(*meta["transform"])
    return {
        "driver": "GTiff",
        "dtype": "float32",
        "count": 1,
        "height": height,
        "width": width,
        "crs": meta["crs"],
        "transform": transform,
        "nodata": NODATA_FLOAT,
        "compress": "DEFLATE",
    }


def _reproject_to_3857(arr: np.ndarray, meta: dict) -> tuple[np.ndarray, dict]:
    """Reproject the array from EPSG:27700 to EPSG:3857 in-memory."""
    src_profile = _src_profile(arr, meta)
    dst_crs = "EPSG:3857"
    dst_transform, dst_width, dst_height = calculate_default_transform(
        src_profile["crs"],
        dst_crs,
        src_profile["width"],
        src_profile["height"],
        *rasterio.transform.array_bounds(
            src_profile["height"], src_profile["width"], src_profile["transform"]
        ),
    )

    arr_filled = np.where(np.isnan(arr) | (arr == 0), NODATA_FLOAT, arr).astype(
        "float32"
    )
    dst = np.full((dst_height, dst_width), NODATA_FLOAT, dtype="float32")
    reproject(
        source=arr_filled,
        destination=dst,
        src_transform=src_profile["transform"],
        src_crs=src_profile["crs"],
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.bilinear,
        src_nodata=NODATA_FLOAT,
        dst_nodata=NODATA_FLOAT,
    )

    dst_profile = {
        **src_profile,
        "crs": dst_crs,
        "transform": dst_transform,
        "width": dst_width,
        "height": dst_height,
    }
    return dst, dst_profile


def write_cog(arr: np.ndarray, profile: dict, out_path: Path) -> None:
    """Write the array to disk as a deflate-compressed COG with overviews."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with MemoryFile() as memfile:
        with memfile.open(**profile) as mem:
            mem.write(arr, 1)

        cog_profile = cog_profiles.get("deflate")
        cog_profile.update(BIGTIFF="IF_SAFER", BLOCKXSIZE=256, BLOCKYSIZE=256)

        cog_translate(
            memfile,
            str(out_path),
            cog_profile,
            in_memory=False,
            overview_level=6,
            overview_resampling="average",
            web_optimized=True,
            quiet=True,
        )


def npy_to_cog(npy_path: Path, meta_path: Path, out_path: Path) -> None:
    arr = load_array(npy_path)
    meta = json.loads(meta_path.read_text())
    arr_3857, profile = _reproject_to_3857(arr, meta)
    write_cog(arr_3857, profile, out_path)
    print(f"  wrote {out_path}  shape={arr_3857.shape}  size_mb={out_path.stat().st_size / 1e6:.2f}")


def delta_to_cog(early: Path, late: Path, meta_path: Path, out_path: Path) -> None:
    a = load_array(early)
    b = load_array(late)
    delta = (b - a).astype("float32")
    delta = np.where(np.isnan(delta) | ((a == 0) & (b == 0)), NODATA_FLOAT, delta)
    meta = json.loads(meta_path.read_text())
    delta_3857, profile = _reproject_to_3857(delta, meta)
    write_cog(delta_3857, profile, out_path)
    print(f"  wrote {out_path}  shape={delta_3857.shape}  size_mb={out_path.stat().st_size / 1e6:.2f}")


def main() -> None:
    p = argparse.ArgumentParser(description="numpy NDVI to Cloud Optimised GeoTIFF")
    p.add_argument("--in", dest="in_path", type=Path)
    p.add_argument("--out", dest="out_path", type=Path, required=True)
    p.add_argument("--meta", type=Path, required=True)
    p.add_argument("--delta", action="store_true", help="compute late minus early")
    p.add_argument("--early", type=Path)
    p.add_argument("--late", type=Path)
    args = p.parse_args()

    if args.delta:
        if not (args.early and args.late):
            raise SystemExit("--delta requires --early and --late")
        delta_to_cog(args.early, args.late, args.meta, args.out_path)
    else:
        if not args.in_path:
            raise SystemExit("--in is required when not using --delta")
        npy_to_cog(args.in_path, args.meta, args.out_path)


if __name__ == "__main__":
    main()
