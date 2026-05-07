import os, zipfile, io, requests
import pandas as pd
import numpy as np
import geopandas as gpd

# Paths
OUT_DIR = "advanced_analysis"
METRICS_CSV = os.path.join(OUT_DIR, "msoa_advanced_metrics.csv")
METRICS_GPKG = os.path.join(OUT_DIR, "msoa_advanced_metrics.gpkg")

def download_correct_population():
    print("Downloading Census 2021 TS001 (Total Usual Residents)...")
    url = "https://www.nomisweb.co.uk/output/census/2021/census2021-ts001.zip"
    r = requests.get(url, timeout=120)
    r.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        # Find the MSOA file
        name = [n for n in zf.namelist() if "msoa" in n.lower() and n.endswith(".csv")][0]
        df = pd.read_csv(zf.open(name))
        
        # Columns in TS001 usually: 
        # [Geography Code, Geography, Usual residents: Total]
        # Let's find the total column explicitly.
        geo_col = [c for c in df.columns if "geography code" in c.lower()][0]
        # The total column is 'Residence type: Total; measures: Value'
        pop_col = [c for c in df.columns if "Residence type: Total" in c][0]
        
        print(f"  Using columns: Geo={geo_col}, Pop={pop_col}")
        
        out = df[[geo_col, pop_col]].copy()
        out.columns = ["MSOA21CD", "population_correct"]
        return out

# 1. Get correct data
pop_df = download_correct_population()

# 2. Load existing metrics
df = pd.read_csv(METRICS_CSV)
df = df.drop(columns=["population", "pop_density", "green_sqm_per_person"])

# 3. Merge and Recalculate
df = df.merge(pop_df, on="MSOA21CD", how="left")
df = df.rename(columns={"population_correct": "population"})

# Recalculate Density
df["pop_density"] = df["population"] / df["area_km2"]

# Recalculate Green Space per Person
# green_area_km2 was already calculated as prop_vegetation * area_km2
df["green_sqm_per_person"] = (df["green_area_km2"] * 1_000_000) / df["population"]
df["green_sqm_per_person"] = df["green_sqm_per_person"].replace([np.inf, -np.inf], np.nan)

# 4. Save
print(f"Corrected Population Mean: {df['population'].mean():.0f}")
print(f"City of London 001 Population: {df.loc[df['MSOA21NM'] == 'City of London 001', 'population'].values[0]}")

df.to_csv(METRICS_CSV, index=False)

# Update GeoPackage
gdf = gpd.read_file(METRICS_GPKG)
geom = gdf[["MSOA21CD", "geometry"]]
final_gdf = geom.merge(df, on="MSOA21CD")
final_gdf.to_file(METRICS_GPKG, driver="GPKG")

print("Metrics corrected successfully.")
