import os, json, warnings, time
from collections import defaultdict
import numpy as np
import rasterio
from rasterio.windows import from_bounds, Window
from rasterio.transform import Affine
from rasterio.enums import Resampling
from rasterio.warp import reproject as rio_reproject
from pyproj import Transformer
from shapely.geometry import box, shape as shp_shape
from shapely.ops import unary_union
import pystac_client
import planetary_computer

warnings.filterwarnings('ignore')

# ======== CONFIGURATION ========
RESOLUTION_M = 20
MAX_CLOUD_COVER = 15
LONDON_BBOX = [-0.51, 51.28, 0.33, 51.69]
BANDS = ["B02", "B03", "B04", "B08"]
S2_SCALE = 0.0001
OUT_DIR = "sentinel_time_series"
os.makedirs(OUT_DIR, exist_ok=True)

catalog = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,
)

def find_best_scenes(year):
    target = box(*LONDON_BBOX)
    
    # Very broad window to find the absolute clearest days
    windows = [
        f"{year}-06-15/{year}-08-15", # Peak Summer
        f"{year}-05-15/{year}-09-15", # Broad Summer
        f"{year}-04-01/{year}-10-31", # Full Growing Season
    ]

    best_overall = None

    for window in windows:
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=LONDON_BBOX,
            datetime=window,
            query={"eo:cloud_cover": {"lt": 20}}, # Initial filter
            max_items=1000,
        )
        items = list(search.items())
        if not items:
            continue

        by_date = defaultdict(list)
        for item in items:
            by_date[item.datetime.strftime("%Y-%m-%d")].append(item)

        candidates = []
        for date_str, date_items in by_date.items():
            combined = unary_union([shp_shape(it.geometry) for it in date_items])
            coverage = combined.intersection(target).area / target.area
            avg_cloud = np.mean([it.properties["eo:cloud_cover"] for it in date_items])
            candidates.append({
                "date": date_str,
                "coverage": coverage,
                "cloud": avg_cloud,
                "items": date_items
            })

        # We strictly want > 98% coverage
        high_cov = [c for c in candidates if c["coverage"] > 0.98]
        
        if high_cov:
            # Sort by cloud cover (lowest first)
            high_cov.sort(key=lambda x: x["cloud"])
            best = high_cov[0]
            
            if best["cloud"] <= 0.1:
                print(f"  Perfect match found! Date: {best['date']} | Cloud: {best['cloud']:.3f}% | Coverage: {best['coverage']:.1%}")
                return best["items"]
            
            # If not 0.1%, keep track of the best one found so far across windows
            if best_overall is None or best["cloud"] < best_overall["cloud"]:
                best_overall = best

    if best_overall:
        print(f"  Note: Could not find 0.1% cloud cover. Picking absolute clearest high-coverage day: {best_overall['date']} ({best_overall['cloud']:.2f}% cloud)")
        return best_overall["items"]

    return None

def read_and_mosaic(scenes, bbox_wgs84, resolution_m):
    dst_crs = "EPSG:27700"
    tf = Transformer.from_crs("EPSG:4326", dst_crs, always_xy=True)
    left, bottom = tf.transform(bbox_wgs84[0], bbox_wgs84[1])
    right, top = tf.transform(bbox_wgs84[2], bbox_wgs84[3])

    out_w = int((right - left) / resolution_m)
    out_h = int((top - bottom) / resolution_m)
    out_transform = Affine(resolution_m, 0, left, 0, -resolution_m, top)

    bands = {}
    for band_name in BANDS:
        mosaic = np.zeros((out_h, out_w), dtype=np.float32)
        count = np.zeros((out_h, out_w), dtype=np.float32)
        for scene in scenes:
            with rasterio.open(scene.assets[band_name].href) as src:
                tf_inv = Transformer.from_crs(dst_crs, src.crs, always_xy=True)
                sl, sb = tf_inv.transform(left, bottom)
                sr, st = tf_inv.transform(right, top)
                src_win = from_bounds(sl, sb, sr, st, src.transform)
                r0, c0 = max(0, int(src_win.row_off)), max(0, int(src_win.col_off))
                r1, c1 = min(src.height, int(src_win.row_off + src_win.height)), min(src.width, int(src_win.col_off + src_win.width))
                if r1 <= r0 or c1 <= c0: continue
                win = Window(c0, r0, c1 - c0, r1 - r0)
                src_data = src.read(1, window=win).astype(np.float32) * S2_SCALE
                src_tf = rasterio.windows.transform(win, src.transform)
                tile = np.zeros((out_h, out_w), dtype=np.float32)
                rio_reproject(source=src_data, destination=tile, src_transform=src_tf, src_crs=src.crs, dst_transform=out_transform, dst_crs=dst_crs, resampling=Resampling.bilinear, src_nodata=0, dst_nodata=0)
                valid = tile > 0
                mosaic[valid] += tile[valid]
                count[valid] += 1
        has_data = count > 0
        mosaic[has_data] /= count[has_data]
        bands[band_name] = mosaic
    return bands

def compute_ndvi(bands):
    nir, red = bands["B08"], bands["B04"]
    denom = nir + red
    return np.where(denom > 0, (nir - red) / denom, 0.0).astype(np.float32)

def download_year(year):
    target = box(*LONDON_BBOX)
    print(f"\nProcessing {year}...")
    
    # 1. Search for scenes (Multiple Tiers)
    search_params = [
        {"query": {"eo:cloud_cover": {"lt": 5}}, "dt": f"{year}-06-01/{year}-08-31"},
        {"query": {"eo:cloud_cover": {"lt": 10}}, "dt": f"{year}-05-01/{year}-09-30"},
        {"query": {"eo:cloud_cover": {"lt": 20}}, "dt": f"{year}-04-01/{year}-10-31"},
    ]
    
    dst_crs = "EPSG:27700"
    tf = Transformer.from_crs("EPSG:4326", dst_crs, always_xy=True)
    left, bottom = tf.transform(LONDON_BBOX[0], LONDON_BBOX[1])
    right, top = tf.transform(LONDON_BBOX[2], LONDON_BBOX[3])
    out_w = int((right - left) / RESOLUTION_M)
    out_h = int((top - bottom) / RESOLUTION_M)
    out_transform = Affine(RESOLUTION_M, 0, left, 0, -RESOLUTION_M, top)

    final_bands = {b: np.zeros((out_h, out_w), dtype=np.float32) for b in ["B03", "B08", "B04"]}
    
    seen_ids = set()

    for tier in search_params:
        mask = (final_bands["B03"] == 0)
        if mask.sum() == 0:
            break
            
        print(f"  Tier {tier['query']['eo:cloud_cover']['lt']}% cloud: {mask.sum():,} pixels left to fill.")
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=LONDON_BBOX,
            datetime=tier["dt"],
            query=tier["query"],
            max_items=100
        )
        items = list(search.items())
        
        # Sort items in this tier by coverage
        def cov_score(item):
            return shp_shape(item.geometry).intersection(target).area / target.area
        items.sort(key=cov_score, reverse=True)

        for item in items:
            if item.id in seen_ids: continue
            
            mask = (final_bands["B03"] == 0)
            if mask.sum() == 0: break
            
            # Check if this item overlaps with the current gaps
            geom = shp_shape(item.geometry)
            if not geom.intersects(target): continue
            
            print(f"    Patching with {item.id}...")
            seen_ids.add(item.id)
            
            for b in ["B03", "B08", "B04"]:
                with rasterio.open(item.assets[b].href) as src:
                    patch = np.zeros((out_h, out_w), dtype=np.float32)
                    rio_reproject(
                        source=rasterio.band(src, 1), destination=patch,
                        src_transform=src.transform, src_crs=src.crs,
                        dst_transform=out_transform, dst_crs=dst_crs,
                        resampling=Resampling.bilinear
                    )
                    patch = patch.astype(np.float32) * 0.0001
                    to_fill = (final_bands[b] == 0) & (patch > 0)
                    final_bands[b][to_fill] = patch[to_fill]

    # Calculate final NDVI
    denom = (final_bands["B08"] + final_bands["B04"])
    ndvi = np.where(denom > 0, (final_bands["B08"] - final_bands["B04"]) / denom, 0.0).astype(np.float32)

    # Save
    np.save(os.path.join(OUT_DIR, f"ndvi_{year}.npy"), ndvi)
    np.save(os.path.join(OUT_DIR, f"band_{year}_B03.npy"), final_bands["B03"])
    np.save(os.path.join(OUT_DIR, f"band_{year}_B08.npy"), final_bands["B08"])
    
    final_mask = (final_bands["B03"] == 0)
    print(f"  Year {year} complete. Final gaps: {final_mask.sum():,} pixels.")
    return True

years = range(2016, 2026)
for year in years:
    download_year(year)

print("\nProcessing complete. Summary saved to sentinel_time_series/summary.json")
