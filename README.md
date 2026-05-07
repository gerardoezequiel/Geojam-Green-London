# Green London

A client-side, deck.gl-powered map of London greenness. Sentinel-2 NDVI, Overture Maps, and ONS census data; every query runs in DuckDB-Wasm in the browser; no backend.

## Status

- [x] Data pack (`geojam_data.zip`, 233 MB, gitignored)
- [x] Source notebooks (data prep + participant)
- [x] Implementation plan ([PLAN.md](PLAN.md))
- [x] Multi-source DuckDB green-areas query ([queries/green_areas.sql](queries/green_areas.sql))
- [ ] Data pipeline run (Phase 0)
- [ ] Next.js app skeleton (Phase 1)

## Quickstart

Open the notebooks in `Data Prep notebooks/` to regenerate `geojam_data.zip`, then run the pipeline:

```sh
cd data-pipeline
uv venv && uv pip install -r requirements.txt
make all
```

## Repo layout

```
.
├── PLAN.md                    # implementation plan and architecture
├── queries/                   # DuckDB-Wasm SQL
│   └── green_areas.sql
├── data-pipeline/             # Python prep
│   ├── Makefile
│   ├── README.md
│   ├── requirements.txt
│   └── src/                   # cog.py, pmtiles.py, h3.py, attrs.py, anomalies.py
├── Data Prep notebooks/       # source notebooks (Colab-friendly)
├── geojam-participant.ipynb   # the GeoJam 2026 challenge notebook
└── geojam_data.zip            # local only, not tracked
```

## Inputs

- **Sentinel-2 L2A** via Microsoft Planetary Computer, two summer dates (2019-07-23, 2024-07-29)
- **MSOA 2021** boundaries from ONS Open Geography Portal
- **Census 2021 population** from NOMIS TS001
- **OSM parks** via OSMnx
- **Overture Maps** divisions and land_use, release 2026-04-15.0, queried directly from S3 us-west-2 by DuckDB-Wasm

## Conventions

British English. No em dashes. No emojis.
