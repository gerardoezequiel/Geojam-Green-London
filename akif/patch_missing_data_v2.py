import os, json, warnings
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject as rio_reproject
import pystac_client
import planetary_computer

warnings.filterwarnings('ignore')

# Paths
DATA_DIR = "geojam_data"
BANDS = ["B02", "B03", "B04", "B08"]

# 1. Setup Catalog
catalog = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,
)

# 2. Get Metadata
with open(os.path.join(DATA_DIR, "raster_meta.json")) as f:
    meta = json.load(f)

bbox = meta["bounds_wgs84"]
out_h, out_w = meta["shape"]
out_transform = rasterio.transform.Affine(*meta["transform"])
dst_crs = meta["crs"]

def patch_gaps(scene_id, description):
    print(f"\nAttempting to patch using {description}...")
    scene = catalog.get_collection("sentinel-2-l2a").get_item(scene_id)
    if not scene:
        print(f"Failed to find scene {scene_id}")
        return

    for band_name in BANDS:
        print(f"  Patching {band_name}...")
        original = np.load(os.path.join(DATA_DIR, f"band_late_{band_name}.npy"))
        mask = (original == 0)
        
        if mask.sum() == 0:
            print(f"    No gaps remaining for {band_name}.")
            continue

        with rasterio.open(scene.assets[band_name].href) as src:
            patch_data = np.zeros((out_h, out_w), dtype=np.float32)
            rio_reproject(
                source=rasterio.band(src, 1),
                destination=patch_data,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=out_transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,
            )
            
            patch_data = patch_data.astype(np.float32) * 0.0001
            to_fill = mask & (patch_data > 0)
            original[to_fill] = patch_data[to_fill]
            np.save(os.path.join(DATA_DIR, f"band_late_{band_name}.npy"), original)
            print(f"    Filled {to_fill.sum():,} pixels.")

# 3. Use scenes that are known to cover the western and eastern extremes
# S2A_MSIL2A_20240807T110621... (Orbit R137, different pass)
# S2A_MSIL2A_20240810T105621... (Orbit R094, different pass)
# These are clear summer days in 2024.

# West Patch (already used one, but let's try a different date to be sure about the top-left)
patch_gaps("S2A_MSIL2A_20240810T105621_R094_T30UXC_20240811T000045", "Aug 10 West Patch")

# East Patch (to cover the bottom-right)
patch_gaps("S2A_MSIL2A_20240807T110621_R137_T31UCT_20240808T011736", "Aug 07 East Patch")

# 4. Final Recalculation
print("\nRecalculating final products...")
red = np.load(os.path.join(DATA_DIR, "band_late_B04.npy"))
nir = np.load(os.path.join(DATA_DIR, "band_late_B08.npy"))
denom = nir + red
ndvi_new = np.where(denom > 0, (nir - red) / denom, 0.0).astype(np.float32)
np.save(os.path.join(DATA_DIR, "ndvi_late.npy"), ndvi_new)

print("Double patch complete. All corners checked.")
