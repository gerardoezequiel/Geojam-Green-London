# Green London — Implementation Plan

A client-side, deck.gl-powered map of London greenness. Driven by Sentinel-2 NDVI, Overture Maps, and ONS census data. No backend; every query runs in DuckDB-Wasm in the browser.

## 1. Data inventory (what we have)

From `geojam_data.zip` (extracted offline; not in repo):

| File | Shape / size | Notes |
|---|---|---|
| `band_early_B0{2,3,4,8}.npy` | 2355 x 2856 float32 | Sentinel-2 L2A, 2019-07-23, 20 m, EPSG:27700 |
| `band_late_B0{2,3,4,8}.npy` | same | 2024-07-29 |
| `ndvi_early.npy`, `ndvi_late.npy` | same | pre-computed, range [-0.85, 0.93] |
| `raster_meta.json` | metadata | affine, CRS, scene IDs |
| `msoa_base.gpkg` | 1011 polygons EPSG:4326 | population, area_km2, pop_density, dist_to_centre_km, dist_to_park_km |
| `msoa_full.gpkg` | same + NDVI stats | mean_ndvi_early/late, mean_delta_ndvi, prop_greener |

One MSOA (Brentwood 003) has no raster coverage. Drop it.

Notebooks already define the modelling task: predict mean_ndvi_late from non-satellite features, surface anomalies via residuals.

## 2. Critical reflection on the green-areas definition

The original BigQuery snippet uses Overture `land_use` filtered to nine subtypes joined to a city polygon by centroid containment. Issues:

1. **Subtype gaps**: misses `forest`, `meadow`, `grass`, `cemetery`, `golf_course`, `pitch`, `farmland`, `orchard`. London's cemeteries (Highgate, Abney Park) and school playing fields are major green reservoirs.
2. **Land cover vs land use**: `land_use` encodes *intent*, not *cover*. Add Overture `base.land_cover` for `tree`, `grass`, `shrub`, `wetland` — these are raster-derived and capture actual surface.
3. **Centroid-in-city join**: drops large polygons whose centroid lies outside (Richmond Park, Lee Valley) and double-counts boundary-crossing ones (Hampstead Heath spans three boroughs). Use `ST_Intersects` for membership and area-weighted overlap (`ST_Area(ST_Intersection(green, borough)) / ST_Area(green)`) for attribution.
4. **`ST_Buffer(_, 0)`** is a BigQuery geometry-repair idiom. In DuckDB-Spatial use `ST_MakeValid(ST_Union_Agg(geom))`.
5. **NDVI vs land-use**: NDVI conflates lawn, crop and tree; cover type matters for ecology and equity. Build the legend from three orthogonal axes: access (public / restricted / private), cover (tree / grass / scrub / water), tier (designated / semi-natural / managed / amenity).
6. **Public vs private greenness**: tagged green polygons miss residential gardens (~24% of London's green per GiGL) and street trees. Derive private-garden greenness from NDVI within residential `land_use` polygons.
7. **Single-date NDVI**: 2019-07-23 vs 2024-07-29 is noisy (phenology, soil moisture, atmospheric). Frame as snapshots, not a trend; compute uncertainty.
8. **Equity metrics**: distance-to-nearest accessible green ≥2 ha (Natural England ANGSt threshold), per-capita green m² at LSOA (aligns with IMD 2019 deciles).

A multi-source DuckDB-friendly definition is in `queries/green_areas.sql`.

## 3. Architecture decisions

### A. Data fabric

- **Pre-baked R2 mirror** for the public site (London bbox, 30–50 MB total). Keeps cold-start fast and EU latency low.
- **Direct Overture S3** (`s3://overturemaps-us-west-2/release/2026-04-15.0/theme=*`) as a "live mode" toggle, queried from DuckDB-Wasm via httpfs for ad-hoc exploration. CORS is open; pin the release version.

### B. Raster delivery

- **deck.gl-raster + COGSource** for NDVI early, late and delta. Float COGs preserve dynamic GLSL ramps (RdYlGn / viridis / RdBu). Three files, ~6 MB each after deflate, hosted on R2.
- **PMTiles vector basemap** (Carto Voyager-style) at all zooms, served from R2 too.

### C. Aggregation

- **Pre-bake stable layers**: `msoa_attrs.parquet`, `lsoa_attrs.parquet`, `h3_res9.parquet`, `anomalies.parquet`. PMTiles for the corresponding geometries.
- **DuckDB-Wasm at runtime** for filters, joins, threshold sliders, percentile rank, derived metrics. No round-trips after the initial parquet bootstrap.

## 4. Layer composition (z-order, zoom visibility)

| Layer | Type | Source | Zoom |
|---|---|---|---|
| Basemap | PMTiles vector | `r2://tiles/basemap.pmtiles` | 0–20 |
| NDVI raster (early or late) | deck.gl-raster | COG, GLSL ramp | 8–13 |
| ΔNDVI raster | deck.gl-raster | COG, divergent ramp | 8–13 |
| MSOA choropleth | MVTLayer | `msoa.pmtiles` + `msoa_attrs.parquet` join | 9–12 |
| LSOA choropleth | MVTLayer | `lsoa.pmtiles` + attrs | 11–14 |
| H3 res-9 | H3HexagonLayer | `h3_res9.parquet` | 13+ |
| Parks overlay | GeoJsonLayer | DuckDB query on `parks_london.parquet` | always |
| Anomaly markers | IconLayer | `anomalies.parquet` | 9+ |
| Selection highlight | GeoJsonLayer | client-side | always |

## 5. Frontend stack

- **Next.js 16 App Router**, single-route SPA with deep-linkable URL state via `nuqs` (`?level=msoa&var=delta&t=2024&bbox=...`). Static export to Vercel.
- **Tailwind CSS + shadcn/ui** primitives. Brand tokens in `theme.config.ts` mirror chrono.city / geospatial.careers shape (CSS custom properties for palette / type / radii). Switching brand swaps one config.
- **deck.gl 9.x** + `@deck.gl/react` overlay + MapLibre GL JS basemap. `deck.gl-raster` (developmentseed) for COGs. PMTiles via `pmtiles` package + `MVTLayer`.
- **DuckDB-Wasm** in a Web Worker, `httpfs` and `spatial` extensions auto-loaded. All filters/joins as SQL.
- **State**: Zustand for ephemeral, `nuqs` for URL-synced.

## 6. Interaction

- Time slider 2019 ↔ 2024 with cross-fade (snapshots, not measurement).
- Aggregation toggle MSOA / LSOA / H3, auto-suggesting the level for current zoom.
- Variable picker: mean NDVI, ΔNDVI, residual, pop density, NDVI per capita, IMD income decile.
- Inspector panel on click: name, all attributes, sparkline, rank within borough, residual flag. Shareable.
- Story mode: five chapters (overview, gainers, losers, equity gap, anomalies) driven by scroll, with `flyTo` camera animations. Respect `prefers-reduced-motion`.
- Accessible colour ramps (colorbrewer cb-safe), keyboard navigation through MSOAs by rank, AA contrast.

## 7. Advanced analyses (ranked by impact × feasibility)

1. **Greenness equity by IMD decile** — LSOA join to IMD 2019; high impact, easy.
2. **Anomaly map** from RandomForest residuals (notebook task); persist residuals to `anomalies.parquet`.
3. **Per-capita green m²** at MSOA + LSOA, from Overture parks area / population.
4. **ANGSt accessibility**: % population within 300 m of public green ≥2 ha.
5. **Tree canopy proxy**: NDVI > 0.6 + spatial-frequency texture filter.
6. **Getis-Ord Gi\*** hot/cold spots at H3 res-9, computed in `pysal` in the prep pipeline.
7. **Borough leaderboards**: 33 boroughs ranked by gain, loss, equity score, anomaly count.
8. **Surprise index** combining model residual + ANGSt deficit. The actionable map.

## 8. Directory layout (next phase)

```
green-london/
  app/
    page.tsx                  # main map
    about/page.tsx            # methodology
    api/og/route.ts           # dynamic Open Graph cards
    layout.tsx
  components/
    map/                      # deck.gl layers, basemap, legend
    panels/                   # inspector, story chapters, controls
    ui/                       # shadcn primitives
  lib/
    duckdb/                   # worker init, query helpers
    layers/                   # layer factories per variable
    state/                    # zustand store, nuqs schema
    theme/                    # theme.config.ts, brand tokens
    variables.ts              # variable registry
  data-pipeline/              # Python, separate venv
    Makefile
    src/{cog,pmtiles,h3,attrs}.py
    notebooks/                # source notebooks (existing)
  queries/                    # SQL for DuckDB-Wasm and prep
  public/                     # tiny bootstrap assets only
```

## 9. Build phases

| Phase | Days | Deliverable |
|---|---|---|
| 0. Pipeline scaffolding | 0.5 | Python venv, Makefile, run prep on existing zip → COGs, PMTiles, parquet under `assets/` |
| 1. Skeleton app | 2 | Next.js, MapLibre + PMTiles basemap, deck.gl overlay, theme tokens, brand-swap config |
| 2. Core layers + DuckDB | 4 | MSOA/LSOA/H3 layers, variable registry, DuckDB worker, legend, hover/click inspector |
| 3. Time + raster | 2 | NDVI COGs via deck.gl-raster, time slider, GLSL ramps |
| 4. Advanced analyses | 3 | residuals, equity, ANGSt, Gi*, leaderboards |
| 5. Story mode + share | 2 | scrolly chapters, OG image API, deep links |
| 6. Polish | 2 | accessibility audit, perf budget, Vercel production |

Total: roughly 15–17 working days.

## 10. Risks and trade-offs

| Risk | Mitigation |
|---|---|
| DuckDB-Wasm cold start (3–5 s) | Show map-only first paint; lazy-load worker; cache compiled module |
| H3 ~80k features in viewport | Server-side bbox prune via DuckDB spatial predicate before passing to deck.gl |
| COG range requests blocked by CORS | Host on R2 with explicit CORS; fallback to PMTiles raster |
| Overture schema drift | Pin release version; CI integration test |
| Brand-swap regressions | Single-source design tokens; Storybook visual regression |
| Mobile GPU limits | Disable raster below 768 px viewport; simplify ramps |
| Two NDVI dates oversells "change" | Frame as snapshots; show per-pixel uncertainty; methodology page |

## 11. References

- Overture release 2026-04-15.0: <https://docs.overturemaps.org/blog/2026/04/15/release-notes/>
- DuckDB 1.5.0 (geometry type built in): <https://duckdb.org/2026/03/09/announcing-duckdb-150.html>
- deck.gl-raster: <https://github.com/developmentseed/deck.gl-raster>
- PMTiles: <https://github.com/protomaps/PMTiles>
- ANGSt: Natural England, *Nature Nearby* (2010)
- IMD 2019: ONS LSOA-level deciles
