# Green London — data pipeline

Offline Python pipeline that turns the GeoJam data pack into web-ready static assets:
COGs for NDVI rasters, PMTiles for MSOA/LSOA boundaries, Parquet for H3 stats and MSOA attributes.

## Setup

```sh
uv venv
uv pip install -r requirements.txt
brew install tippecanoe pmtiles  # for PMTiles generation
```

## Run

```sh
make all       # build everything under ../assets/
make cogs      # NDVI 2019, 2024, delta as Cloud Optimised GeoTIFF
make pmtiles   # MSOA + LSOA tilesets
make parquet   # MSOA attributes + anomalies
make h3        # H3 res-9 with NDVI per cell
make clean
```

## Output

```
assets/
  cogs/ndvi_{2019,2024,delta}.tif         # ~6 MB each
  pmtiles/{msoa,lsoa}.pmtiles              # 3-25 MB
  parquet/{msoa_attrs,anomalies,h3_res9}.parquet
```

Upload to Cloudflare R2 with `wrangler r2 object put` or `aws s3 cp` against the R2 endpoint.
CORS must allow the production domain plus localhost for dev.

## Modules

- `src/cog.py` — numpy NDVI to deflate-compressed COG via rio-cogeo
- `src/pmtiles.py` — GeoPackage to PMTiles via tippecanoe
- `src/attrs.py` — geometry-free attribute table to Parquet
- `src/h3.py` — h3-py polyfill of MSOA polygons + NDVI sampling
- `src/anomalies.py` — train RandomForest on non-satellite features, persist residuals

See `../PLAN.md` for the wider architecture and `../queries/green_areas.sql` for the runtime DuckDB queries.
