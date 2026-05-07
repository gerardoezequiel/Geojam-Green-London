import os, json, warnings
import numpy as np
import pandas as pd
import geopandas as gpd
from rasterstats import zonal_stats
from rasterio.transform import Affine

warnings.filterwarnings('ignore')

# Paths
DATA_DIR = "geojam_data"
TS_DIR = "sentinel_time_series"
OUT_DIR = "final_results"
os.makedirs(OUT_DIR, exist_ok=True)

# 1. Load Metadata and Base MSOA
with open(os.path.join(DATA_DIR, "raster_meta.json")) as f:
    meta = json.load(f)
aff = Affine(*meta["transform"])
msoa = gpd.read_file(os.path.join(DATA_DIR, "msoa_base.gpkg"))
msoa_proj = msoa.to_crs(meta["crs"])

# Re-fetch the correct population from our previously fixed file or NOMIS logic
# (Using the CSV we fixed earlier as the source for correct population)
prev_metrics = pd.read_csv("advanced_analysis/msoa_advanced_metrics.csv")
pop_map = prev_metrics.set_index("MSOA21CD")["population"].to_dict()

# 2. Re-calculate High-Fidelity Time Series (Mean NDVI)
# Using the _norm.npy files for stability
years = range(2016, 2026)
metrics = pd.DataFrame({"MSOA21CD": msoa["MSOA21CD"], "MSOA21NM": msoa["MSOA21NM"]})

print("Calculating high-fidelity zonal stats...")
for y in years:
    path = os.path.join(TS_DIR, f"ndvi_{y}_norm.npy")
    if os.path.exists(path):
        ndvi = np.load(path)
        stats = zonal_stats(msoa_proj.geometry, ndvi, affine=aff, stats=["mean"], nodata=0.0)
        metrics[f"ndvi_{y}"] = [s["mean"] for s in stats]

# 3. Derive Strategic Metrics
metrics["population"] = metrics["MSOA21CD"].map(pop_map)
metrics["area_km2"] = msoa["area_km2"]

# Long-term Change (2016 -> 2025)
metrics["total_greening"] = metrics["ndvi_2025"] - metrics["ndvi_2016"]

# Current Equity (2025)
# We use the normalized NDVI > 0.25 as a proxy for 'Green Area'
path_2025 = os.path.join(TS_DIR, f"ndvi_2025_norm.npy")
ndvi_2025 = np.load(path_2025)
veg_mask = (ndvi_2025 > 0.25).astype(np.float32)
stats_veg = zonal_stats(msoa_proj.geometry, veg_mask, affine=aff, stats=["mean"], nodata=0.0)
metrics["prop_vegetation"] = [s["mean"] for s in stats_veg]
metrics["green_area_sqm"] = metrics["prop_vegetation"] * metrics["area_km2"] * 1_000_000
metrics["green_sqm_per_person"] = metrics["green_area_sqm"] / metrics["population"]
metrics["green_sqm_per_person"] = metrics["green_sqm_per_person"].replace([np.inf, -np.inf], np.nan)

# 4. Aggregate to Boroughs
metrics["borough"] = metrics["MSOA21NM"].str.extract(r'^(.+?)\s\d+$')[0]
borough_stats = metrics.groupby("borough").agg({
    "population": "sum",
    "green_area_sqm": "sum",
    "total_greening": "mean",
    "ndvi_2025": "mean"
}).reset_index()
borough_stats["green_sqm_per_person"] = borough_stats["green_area_sqm"] / borough_stats["population"]

# 5. Save Final Assets
metrics.to_csv(os.path.join(OUT_DIR, "london_final_msoa_metrics.csv"), index=False)
borough_stats.to_csv(os.path.join(OUT_DIR, "london_borough_leaderboard.csv"), index=False)

# Spatial export
final_gdf = msoa.merge(metrics.drop(columns=["MSOA21NM", "area_km2"]), on="MSOA21CD")
final_gdf.to_file(os.path.join(OUT_DIR, "london_final_spatial_data.gpkg"), driver="GPKG")

print(f"\nFinal Analysis complete. Files saved to {OUT_DIR}/")
