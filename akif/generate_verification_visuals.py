import os, json
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

# Paths
ADV_DIR = "advanced_analysis"
OUT_DIR = "verification_visuals"
os.makedirs(OUT_DIR, exist_ok=True)

# 1. Load Data
gdf = gpd.read_file(os.path.join(ADV_DIR, "msoa_advanced_metrics.gpkg"))
clusters = np.load(os.path.join(ADV_DIR, "land_cover_clusters.npy"))
with open(os.path.join(ADV_DIR, "cluster_legend.json")) as f:
    legend = json.load(f)

# 2. EQUITY MAP
print("Generating Equity Map...")
fig, ax = plt.subplots(1, 1, figsize=(15, 10))
gdf.plot(column="green_sqm_per_person", cmap="RdYlGn", scheme="quantiles", ax=ax)
sm = plt.cm.ScalarMappable(cmap="RdYlGn", norm=plt.Normalize(vmin=gdf["green_sqm_per_person"].min(), vmax=gdf["green_sqm_per_person"].max()))
fig.colorbar(sm, ax=ax, orientation="horizontal", label="Green Space (sqm) per Person", shrink=0.6)
ax.set_title("Environmental Equity in London: Green Space Access per Resident", fontsize=16)
ax.axis("off")
plt.savefig(os.path.join(OUT_DIR, "equity_map.png"), dpi=200, bbox_inches="tight")
plt.close()

# 3. TIME SERIES TREND
print("Generating Time Series Trend...")
ndvi_cols = sorted([c for c in gdf.columns if c.startswith("ndvi_")])
years = [int(c.split("_")[1]) for c in ndvi_cols]
mean_trend = [gdf[c].mean() for c in ndvi_cols]
plt.figure(figsize=(10, 6))
plt.plot(years, mean_trend, marker='o', color='forestgreen', linewidth=2)
plt.title("London-wide Greenness Trend (2015-2025)", fontsize=14)
plt.ylabel("Mean NDVI (Greenness)")
plt.xlabel("Year")
plt.grid(True, linestyle='--', alpha=0.7)
plt.savefig(os.path.join(OUT_DIR, "time_series_trend.png"), dpi=200, bbox_inches="tight")
plt.close()

# 4. LAND COVER CLUSTERS (Rule-Based, 5 Clean Colors)
print("Generating Cluster Map...")
# 0=Black, 1=Grey, 2=LightGreen, 3=DarkGreen, 4=Blue, 5=White
colors = ["black", "grey", "#90EE90", "forestgreen", "royalblue", "white"]
cmap = ListedColormap(colors)

plt.figure(figsize=(15, 12))
plt.imshow(clusters, cmap=cmap, vmin=0, vmax=5)
plt.title("London Land Cover Classification (Rule-Based)", fontsize=16)
plt.axis("off")

# Legend patches
from matplotlib.patches import Patch
legend_elements = [
    Patch(facecolor="grey", label="Built Environment"),
    Patch(facecolor="#90EE90", label="Grass/Parkland"),
    Patch(facecolor="forestgreen", label="Trees/Woodland"),
    Patch(facecolor="royalblue", label="Water"),
    Patch(facecolor="white", label="Clouds/Noise")
]
plt.legend(handles=legend_elements, loc='upper right', frameon=True, fontsize=12)
plt.savefig(os.path.join(OUT_DIR, "clusters_map.png"), dpi=300, bbox_inches="tight")
plt.close()

print(f"Verification visuals generated in {OUT_DIR}/")
