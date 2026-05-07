import os, json, warnings
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch

warnings.filterwarnings('ignore')

# Paths
TS_DIR = "sentinel_time_series"
OUT_DIR = "annual_verification_maps"
os.makedirs(OUT_DIR, exist_ok=True)

# Colors: 0=Black, 1=Grey, 2=LightGreen, 3=DarkGreen, 4=Blue, 5=White
colors = ["black", "grey", "#90EE90", "forestgreen", "royalblue", "white"]
cmap = ListedColormap(colors)
legend_elements = [
    Patch(facecolor="grey", label="Built Environment"),
    Patch(facecolor="#90EE90", label="Grass/Parkland"),
    Patch(facecolor="forestgreen", label="Trees/Woodland"),
    Patch(facecolor="royalblue", label="Water"),
    Patch(facecolor="white", label="Clouds/Noise")
]

def process_year(year):
    print(f"  Processing {year}...")
    try:
        # Prioritize normalized data for visual consistency
        norm_path = os.path.join(TS_DIR, f"ndvi_{year}_norm.npy")
        if os.path.exists(norm_path):
            ndvi = np.load(norm_path)
            title_suffix = "(Normalized)"
        else:
            ndvi = np.load(os.path.join(TS_DIR, f"ndvi_{year}.npy"))
            title_suffix = ""
            
        b03 = np.load(os.path.join(TS_DIR, f"band_{year}_B03.npy"))
        b08 = np.load(os.path.join(TS_DIR, f"band_{year}_B08.npy"))
    except FileNotFoundError:
        print(f"    Bands not found for {year} yet. Skipping.")
        return

    # 1. Rule-Based Classification
    classification = np.ones(ndvi.shape, dtype=np.int8)

    # NDWI for Water
    denom = (b03 + b08)
    ndwi = np.where(denom > 0, (b03 - b08) / denom, -1)

    # Vegetation (Using normalized NDVI)
    classification[(ndvi > 0.25) & (ndvi <= 0.45)] = 2
    classification[ndvi > 0.45] = 3

    # Water
    classification[(ndwi > 0.0) & (ndvi < 0.1) & (b08 < 0.15)] = 4

    # Plotting
    plt.figure(figsize=(15, 12))
    plt.imshow(classification, cmap=cmap, vmin=0, vmax=5)
    plt.title(f"London Land Cover - {year} {title_suffix}", fontsize=20)
    plt.axis("off")
    plt.legend(handles=legend_elements, loc='upper right', frameon=True, fontsize=12)
    
    plt.savefig(os.path.join(OUT_DIR, f"map_{year}.png"), dpi=150, bbox_inches="tight")
    plt.close()

available_years = sorted([int(f.split("_")[1].split(".")[0]) for f in os.listdir(TS_DIR) if f.startswith("ndvi_")])

print(f"Applying Refined Methodology to {len(available_years)} years...")
for year in available_years:
    process_year(year)

print(f"\nRefined annual maps generated in {OUT_DIR}/")
