import os, json
import numpy as np
import pandas as pd
import geopandas as gpd
from rasterstats import zonal_stats
from rasterio.transform import Affine

# Paths
DATA_DIR = "geojam_data"
TS_DIR = "sentinel_time_series"
OUT_DIR = "advanced_analysis"
os.makedirs(OUT_DIR, exist_ok=True)

# Load base MSOA and raster meta
msoa = gpd.read_file(os.path.join(DATA_DIR, "msoa_base.gpkg"))
with open(os.path.join(DATA_DIR, "raster_meta.json")) as f:
    meta = json.load(f)

aff = Affine(*meta["transform"])
raster_crs = meta["crs"]
msoa_proj = msoa.to_crs(raster_crs)

# 1. TIME SERIES NDVI & DELTA
print("Processing annual NDVI time series...")
ts_results = pd.DataFrame({"MSOA21CD": msoa["MSOA21CD"]})

available_years = sorted([int(f.split("_")[1].split(".")[0]) for f in os.listdir(TS_DIR) if f.startswith("ndvi_")])

for year in available_years:
    ndvi = np.load(os.path.join(TS_DIR, f"ndvi_{year}.npy"))
    stats = zonal_stats(msoa_proj.geometry, ndvi, affine=aff, stats=["mean"], nodata=0.0)
    ts_results[f"ndvi_{year}"] = [s["mean"] for s in stats]
    print(f"  {year} processed.")

# Calculate 2015-2024 Delta (or latest available)
if len(available_years) >= 2:
    y_start, y_end = available_years[0], available_years[-1]
    ts_results["delta_ndvi_longterm"] = ts_results[f"ndvi_{y_end}"] - ts_results[f"ndvi_{y_start}"]

# 2. SPECTRAL FEATURES (Water, Soil, Vegetation)
# Simple Thresholding based on 2024 (late) data
print("Deriving land cover features...")
ndvi_late = np.load(os.path.join(DATA_DIR, "ndvi_late.npy"))
# Water: NDVI < 0 (typically)
# Bare Soil/Built: 0 <= NDVI < 0.2
# Vegetation: NDVI >= 0.2

water_mask = (ndvi_late < 0).astype(np.float32)
vegetation_mask = (ndvi_late >= 0.2).astype(np.float32)
soil_built_mask = ((ndvi_late >= 0) & (ndvi_late < 0.2)).astype(np.float32)

def get_prop(mask):
    return [s["mean"] for s in zonal_stats(msoa_proj.geometry, mask, affine=aff, stats=["mean"], nodata=0.0)]

ts_results["prop_water"] = get_prop(water_mask)
ts_results["prop_vegetation"] = get_prop(vegetation_mask)
ts_results["prop_built_soil"] = get_prop(soil_built_mask)

# 3. ENVIRONMENTAL EQUITY (Green Space per Person)
print("Calculating equity metrics...")
# Green Area (km2) = prop_vegetation * area_km2
ts_results = ts_results.merge(msoa[["MSOA21CD", "area_km2", "population"]], on="MSOA21CD")
ts_results["green_area_km2"] = ts_results["prop_vegetation"] * ts_results["area_km2"]
ts_results["green_sqm_per_person"] = (ts_results["green_area_km2"] * 1_000_000) / ts_results["population"]

# Handle division by zero for unpopulated MSOAs (like parks/industrial)
ts_results["green_sqm_per_person"] = ts_results["green_sqm_per_person"].replace([np.inf, -np.inf], np.nan)

# Save to DuckDB-friendly CSV or GeoPackage
final_msoa = msoa.merge(ts_results.drop(columns=["area_km2", "population"]), on="MSOA21CD")
final_msoa.to_file(os.path.join(OUT_DIR, "msoa_advanced_metrics.gpkg"), driver="GPKG")
final_msoa.drop(columns="geometry").to_csv(os.path.join(OUT_DIR, "msoa_advanced_metrics.csv"), index=False)

print(f"\nAnalysis complete. Results saved to {OUT_DIR}/")
print(f"Columns added: {list(ts_results.columns)}")
