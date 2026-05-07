import os, json
import numpy as np

# Paths
DATA_DIR = "geojam_data"
OUT_DIR = "advanced_analysis"

# 1. Load Data
print("Loading 2024 Sentinel-2 bands...")
b02 = np.load(os.path.join(DATA_DIR, "band_late_B02.npy"))
b03 = np.load(os.path.join(DATA_DIR, "band_late_B03.npy"))
b04 = np.load(os.path.join(DATA_DIR, "band_late_B04.npy"))
b08 = np.load(os.path.join(DATA_DIR, "band_late_B08.npy"))
ndvi = np.load(os.path.join(DATA_DIR, "ndvi_late.npy"))

# Mask for valid pixels (not zero)
mask = (b02 > 0)

# 2. Rule-Based Classification
classification = np.ones(b02.shape, dtype=np.int8)

# Calculate NDWI (Normalized Difference Water Index) for better river detection
# NDWI = (Green - NIR) / (Green + NIR)
ndwi = (b03 - b08) / (b03 + b08)

# B. Vegetation (NDVI based)
classification[(ndvi > 0.25) & (ndvi <= 0.45)] = 2
classification[ndvi > 0.45] = 3

# C. Water (Stricter constraints to avoid urban false positives)
# Water should have positive NDWI, very low NDVI, and low NIR reflectance.
classification[(ndwi > 0.0) & (ndvi < 0.1) & (b08 < 0.15)] = 4

# D. Clouds (Brightest pixels)
classification[(b02 > 0.4) & (b03 > 0.4) & (b04 > 0.4)] = 5

# 3. Save Results
np.save(os.path.join(OUT_DIR, "land_cover_clusters.npy"), classification)

legend = {
    "1": "Built Environment",
    "2": "Grass/Parkland",
    "3": "Trees/Woodland",
    "4": "Water",
    "5": "Clouds/Noise"
}

with open(os.path.join(OUT_DIR, "cluster_legend.json"), "w") as f:
    json.dump(legend, f, indent=2)

print("\nRule-Based Land Cover Classification complete.")
print(f"Counts: Built: {(classification==1).sum():,}, Grass: {(classification==2).sum():,}, Trees: {(classification==3).sum():,}, Water: {(classification==4).sum():,}")
