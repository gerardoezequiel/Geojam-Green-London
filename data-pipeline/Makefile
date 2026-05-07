.PHONY: all clean cogs pmtiles parquet h3

DATA      := geojam_data
ASSETS    := ../assets
COGS      := $(ASSETS)/cogs
PMTILES   := $(ASSETS)/pmtiles
PARQUET   := $(ASSETS)/parquet

all: cogs pmtiles parquet h3

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

clean:
	rm -rf $(ASSETS)
