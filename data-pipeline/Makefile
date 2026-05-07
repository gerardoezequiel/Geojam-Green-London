.PHONY: all clean cogs pmtiles parquet h3 timeseries equity clusters spectral

DATA      := geojam_data
ASSETS    := ../assets
COGS      := $(ASSETS)/cogs
PMTILES   := $(ASSETS)/pmtiles
PARQUET   := $(ASSETS)/parquet

all: cogs pmtiles parquet h3 spectral clusters timeseries equity

$(ASSETS):
	mkdir -p $(COGS) $(PMTILES) $(PARQUET)

cogs: $(ASSETS)
	uv run python src/cog.py \
	  --in ../$(DATA)/ndvi_early.npy --out $(COGS)/ndvi_2019.tif \
	  --meta ../$(DATA)/raster_meta.json
	uv run python src/cog.py \
	  --in ../$(DATA)/ndvi_late.npy --out $(COGS)/ndvi_2024.tif \
	  --meta ../$(DATA)/raster_meta.json
	uv run python src/cog.py \
	  --delta --early ../$(DATA)/ndvi_early.npy --late ../$(DATA)/ndvi_late.npy \
	  --out $(COGS)/ndvi_delta.tif --meta ../$(DATA)/raster_meta.json

pmtiles: $(ASSETS)
	uv run python src/pmtiles.py --in ../$(DATA)/msoa_full.gpkg --out $(PMTILES)/msoa.pmtiles --layer msoa
	uv run python src/pmtiles.py --in lsoa_london.geojson         --out $(PMTILES)/lsoa.pmtiles --layer lsoa

parquet: $(ASSETS)
	uv run python src/attrs.py  --in ../$(DATA)/msoa_full.gpkg --out $(PARQUET)/msoa_attrs.parquet
	uv run python src/anomalies.py --notebook ../geojam-participant.ipynb --out $(PARQUET)/anomalies.parquet

h3: $(ASSETS)
	uv run python src/h3.py \
	  --boundaries ../$(DATA)/msoa_full.gpkg \
	  --rasters $(COGS)/ndvi_2019.tif $(COGS)/ndvi_2024.tif $(COGS)/ndvi_delta.tif \
	  --resolution 9 --out $(PARQUET)/h3_res9.parquet

spectral: $(ASSETS)
	uv run python src/spectral.py \
	  --bands ../$(DATA)/band_late_B02.npy ../$(DATA)/band_late_B03.npy \
	          ../$(DATA)/band_late_B04.npy ../$(DATA)/band_late_B08.npy \
	  --boundaries ../$(DATA)/msoa_full.gpkg \
	  --out $(PARQUET)/msoa_spectral.parquet

clusters: $(ASSETS)
	uv run python src/clusters.py \
	  --bands ../$(DATA)/band_late_B02.npy ../$(DATA)/band_late_B03.npy \
	          ../$(DATA)/band_late_B04.npy ../$(DATA)/band_late_B08.npy \
	  --k 6 --out-cog $(COGS)/clusters_2024.tif \
	  --out-parquet $(PARQUET)/msoa_clusters.parquet

timeseries: $(ASSETS)
	uv run python src/timeseries.py \
	  --bbox -0.51 51.28 0.33 51.69 \
	  --years 2017 2018 2019 2020 2021 2022 2023 2024 2025 \
	  --resolution 9 \
	  --out $(PARQUET)/h3_ndvi_timeseries.parquet

equity: $(ASSETS)
	uv run python src/equity.py \
	  --os-greenspace data/OS_OpenGreenspace.zip \
	  --imd data/IMD_2019.csv \
	  --lsoa data/LSOA_2021.gpkg \
	  --population data/Census_2021_LSOA_TS001.csv \
	  --out $(PARQUET)/lsoa_equity.parquet

clean:
	rm -rf $(ASSETS)
