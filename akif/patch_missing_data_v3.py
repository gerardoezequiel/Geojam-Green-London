import os, json, warnings
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject as rio_reproject
import pystac_client
import planetary_computer

warnings.filterwarnings('ignore')

DATA_DIR = "geojam_data"
BANDS = ["B02", "B03", "B04", "B08"]

catalog = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,
)

with open(os.path.join(DATA_DIR, "raster_meta.json")) as f:
    meta = json.load(f)

bbox = meta["bounds_wgs84"]
out_h, out_w = meta["shape"]
out_transform = rasterio.transform.Affine(*meta["transform"])
dst_crs = meta["crs"]

def robust_patch():
    # Find ANY clear scene in summer 2024 that covers our bbox
    print("Searching for any high-coverage clear scenes in 2024...")
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime="2024-05-01/2024-09-30",
        query={"eo:cloud_cover": {"lt": 5}},
        max_items=50
    )
    items = list(search.items())
    print(f"Found {len(items)} candidate tiles.")

    for band_name in BANDS:
        print(f"\nProcessing {band_name}...")
        original = np.load(os.path.join(DATA_DIR, f"band_late_{band_name}.npy"))
        
        for item in items:
            mask = (original == 0)
            if mask.sum() == 0:
                break
                
            print(f"  Attempting patch with {item.id} ({mask.sum():,} gaps left)")
            try:
                with rasterio.open(item.assets[band_name].href) as src:
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
            except Exception as e:
                print(f"    Error with scene {item.id}: {e}")
        
        np.save(os.path.join(DATA_DIR, f"band_late_{band_name}.npy"), original)

    print("\nRecalculating NDVI...")
    red = np.load(os.path.join(DATA_DIR, "band_late_B04.npy"))
    nir = np.load(os.path.join(DATA_DIR, "band_late_B08.npy"))
    denom = nir + red
    ndvi_new = np.where(denom > 0, (nir - red) / denom, 0.0).astype(np.float32)
    np.save(os.path.join(DATA_DIR, "ndvi_late.npy"), ndvi_new)

robust_patch()
print("\nMulti-scene coverage patch complete.")
