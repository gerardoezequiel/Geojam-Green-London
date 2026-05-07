import os, json, warnings
import numpy as np
import pandas as pd
import geopandas as gpd

warnings.filterwarnings('ignore')

# Paths
TS_DIR = "sentinel_time_series"
DATA_DIR = "geojam_data"
OUT_DIR = "advanced_analysis"

# Load MSOA base for zonal stats
msoa = gpd.read_file(os.path.join(DATA_DIR, "msoa_base.gpkg"))

def normalize_time_series():
    available_years = sorted([int(f.split("_")[1].split(".")[0]) for f in os.listdir(TS_DIR) if f.startswith("ndvi_")])
    print(f"Normalizing {len(available_years)} years...")

    # 1. First, we identify a 'Reference Year' (e.g., 2024 or 2016)
    # or we normalize to the overall mean.
    # We will use 'Histogram Matching' or 'Global Mean Scaling'
    
    yearly_means = {}
    for year in available_years:
        ndvi = np.load(os.path.join(TS_DIR, f"ndvi_{year}.npy"))
        # Only consider non-zero pixels for the mean
        valid_mask = (ndvi != 0)
        if valid_mask.any():
            yearly_means[year] = np.mean(ndvi[valid_mask])
        else:
            yearly_means[year] = 0

    global_mean = np.mean(list(yearly_means.values()))
    print(f"Global NDVI Mean: {global_mean:.4f}")

    normalized_stats = pd.DataFrame({"MSOA21CD": msoa["MSOA21CD"]})

    for year in available_years:
        ndvi = np.load(os.path.join(TS_DIR, f"ndvi_{year}.npy"))
        
        # Apply scaling factor to bring this year in line with the global mean
        # This removes the 'haze' or 'seasonal' flicker
        factor = global_mean / yearly_means[year] if yearly_means[year] != 0 else 1.0
        print(f"  {year}: Scaling by {factor:.3f} (Mean: {yearly_means[year]:.3f})")
        
        # Scale the data (clamping to valid NDVI range -1 to 1)
        ndvi_norm = np.clip(ndvi * factor, -1.0, 1.0).astype(np.float32)
        
        # Save normalized raster for the maps
        np.save(os.path.join(TS_DIR, f"ndvi_{year}_norm.npy"), ndvi_norm)
        
    print("\nNormalization complete. Normalized rasters saved with '_norm.npy' suffix.")

if __name__ == "__main__":
    normalize_time_series()
