import os, json, warnings
import numpy as np
import rasterio
from rasterio.windows import from_bounds, Window
from rasterio.transform import Affine
from rasterio.enums import Resampling
from rasterio.warp import reproject as rio_reproject
from pyproj import Transformer
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

# 2. Get Metadata for original mosaic
with open(os.path.join(DATA_DIR, "raster_meta.json")) as f:
    meta = json.load(f)

bbox = meta["bounds_wgs84"]
res = meta["resolution_m"]
out_h, out_w = meta["shape"]
out_transform = Affine(*meta["transform"])
dst_crs = meta["crs"]

# 3. Find a scene that covers the LEFT edge specifically
# We search for a different orbit (R094 usually covers the west)
print("Searching for patch scenes for the western edge...")
search = catalog.search(
    collections=["sentinel-2-l2a"],
    bbox=[bbox[0], bbox[1], bbox[0] + 0.1, bbox[3]], # Search narrow strip on left
    datetime="2024-06-01/2024-08-31",
    query={"eo:cloud_cover": {"lt": 5}},
    max_items=10,
)
items = list(search.items())
# Avoid the original date
patch_items = [it for it in items if it.datetime.strftime("%Y-%m-%d") != "2024-07-29"]

if not patch_items:
    print("No suitable patch scenes found. Trying a broader window...")
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=[bbox[0], bbox[1], bbox[0] + 0.1, bbox[3]],
        datetime="2024-04-01/2024-10-31",
        query={"eo:cloud_cover": {"lt": 10}},
        max_items=20,
    )
    patch_items = [it for it in list(search.items()) if it.datetime.strftime("%Y-%m-%d") != "2024-07-29"]

if not patch_items:
    print("Fatal: Could not find any data for the western corner.")
    exit(1)

# Pick the first one
patch_scene = patch_items[0]
print(f"Using {patch_scene.id} from {patch_scene.datetime.strftime('%Y-%m-%d')} to patch the hole.")

# 4. Patch the bands
for band_name in BANDS:
    print(f"  Patching {band_name}...")
    original = np.load(os.path.join(DATA_DIR, f"band_late_{band_name}.npy"))
    mask = (original == 0)
    
    if mask.sum() == 0:
        continue

    with rasterio.open(patch_scene.assets[band_name].href) as src:
        # Reproject the patch data into our mosaic space
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
        
        # Sentinel-2 scale factor (1/10000)
        patch_data = patch_data.astype(np.float32) * 0.0001
        
        # Fill only where original was 0 and patch has data
        valid_patch = (patch_data > 0)
        to_fill = mask & valid_patch
        original[to_fill] = patch_data[to_fill]
        
        # Save back
        np.save(os.path.join(DATA_DIR, f"band_late_{band_name}.npy"), original)

# 5. Recalculate late NDVI
print("Recalculating late NDVI...")
red = np.load(os.path.join(DATA_DIR, "band_late_B04.npy"))
nir = np.load(os.path.join(DATA_DIR, "band_late_B08.npy"))
denom = nir + red
ndvi_new = np.where(denom > 0, (nir - red) / denom, 0.0).astype(np.float32)
np.save(os.path.join(DATA_DIR, "ndvi_late.npy"), ndvi_new)

print("Patch complete. Holes filled.")
