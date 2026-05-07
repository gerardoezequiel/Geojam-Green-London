import os, json
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt

# Paths
FINAL_DIR = "final_results"
OUT_DIR = "strategic_maps"
os.makedirs(OUT_DIR, exist_ok=True)

# 1. Load Data
gdf = gpd.read_file(os.path.join(FINAL_DIR, "london_final_spatial_data.gpkg"))

# 2. STRATEGIC MAP 1: ENVIRONMENTAL EQUITY (2025)
print("Generating Final Equity Map...")
fig, ax = plt.subplots(1, 1, figsize=(15, 12))
gdf.plot(column="green_sqm_per_person", cmap="RdYlGn", scheme="quantiles", k=7, ax=ax)
sm = plt.cm.ScalarMappable(cmap="RdYlGn", norm=plt.Normalize(vmin=0, vmax=gdf["green_sqm_per_person"].quantile(0.95)))
fig.colorbar(sm, ax=ax, orientation="horizontal", label="Green Area (sqm) per Resident", shrink=0.5, pad=0.01)
ax.set_title("Environmental Equity in London (2025)\nGreen Space Access per Person", fontsize=18, pad=20)
ax.axis("off")
plt.savefig(os.path.join(OUT_DIR, "equity_map_2025.png"), dpi=200, bbox_inches="tight")
plt.close()

# 3. STRATEGIC MAP 2: GREENING HOTSPOTS (2016-2025)
print("Generating Greening Hotspots Map...")
fig, ax = plt.subplots(1, 1, figsize=(15, 12))
# RdBu_r: Red for loss (greying), Blue for gain (greening)
gdf.plot(column="total_greening", cmap="RdYlGn", scheme="quantiles", k=7, ax=ax)
sm = plt.cm.ScalarMappable(cmap="RdYlGn", norm=plt.Normalize(vmin=gdf["total_greening"].min(), vmax=gdf["total_greening"].max()))
fig.colorbar(sm, ax=ax, orientation="horizontal", label="Change in Greenness (NDVI Delta)", shrink=0.5, pad=0.01)
ax.set_title("10-Year Greening Hotspots (2016-2025)\nWhere London is getting greener vs. greyer", fontsize=18, pad=20)
ax.axis("off")
plt.savefig(os.path.join(OUT_DIR, "greening_hotspots_10year.png"), dpi=200, bbox_inches="tight")
plt.close()

# 4. STRATEGIC REPORT: BOROUGH LEADERBOARD
print("Generating Borough Summary...")
leaderboard = pd.read_csv(os.path.join(FINAL_DIR, "london_borough_leaderboard.csv"))
leaderboard = leaderboard.sort_values("green_sqm_per_person", ascending=False)

with open(os.path.join(OUT_DIR, "borough_strategic_brief.txt"), "w") as f:
    f.write("LONDON GREEN STRATEGY BRIEF (2025)\n")
    f.write("===================================\n\n")
    f.write("TOP 5 MOST EQUITABLE BOROUGHS (Green sqm/person):\n")
    for i, row in leaderboard.head(5).iterrows():
        f.write(f"{i+1}. {row['borough']:20s} | {row['green_sqm_per_person']:,.1f} sqm/person\n")
    
    f.write("\nBOTTOM 5 LEAST EQUITABLE BOROUGHS (Green sqm/person):\n")
    for i, row in leaderboard.tail(5).iterrows():
        f.write(f"{i+1}. {row['borough']:20s} | {row['green_sqm_per_person']:,.1f} sqm/person\n")
    
    f.write("\nMOST IMPROVED BOROUGHS (Greening Trend 2016-2025):\n")
    top_gainers = leaderboard.sort_values("total_greening", ascending=False).head(5)
    for i, row in top_gainers.iterrows():
        f.write(f"{i+1}. {row['borough']:20s} | +{row['total_greening']:.3f} NDVI gain\n")

print(f"Strategic maps and report generated in {OUT_DIR}/")
