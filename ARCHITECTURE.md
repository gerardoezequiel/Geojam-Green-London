# Green Cities — Architecture

A multi-city, mostly-static, browser-first geospatial application. Same SQL on the server (dbt-duckdb) and in the browser (DuckDB-Wasm). London is the reference city; Berlin and Paris drop in via a manifest.

## 0. TL;DR

- **Renderers**: MapLibre GL JS for the basemap and viewport; deck.gl interleaved as `MapboxOverlay` for data layers; deck.gl-raster for NDVI COGs; H3HexagonLayer for hex stats. Yes, MapLibre is needed.
- **Compute**: DuckDB-Wasm in a Web Worker for runtime queries. Same SQL runs server-side via dbt-duckdb in CI. The `raster` community extension lets us do NDVI / zonal stats / clipping in pure SQL.
- **Storage**: Cloudflare R2 for COGs, PMTiles, Parquet. Zero egress, global CDN. Overture Maps stays on `s3://overturemaps-us-west-2/` and is queried directly via `httpfs`.
- **Pipeline**: medallion (bronze → silver → gold) materialised by dbt-duckdb, orchestrated by GitHub Actions on a weekly cron, infra defined in Terraform.
- **Frontend**: Next.js 16 App Router on Vercel, static export per city, brand-swappable design tokens.

## 1. Multi-city generalisation

### 1.1 What changes per city

| Layer | London | Berlin | Paris |
|---|---|---|---|
| Equal-area CRS | EPSG:27700 (BNG) | EPSG:25832 (ETRS89-UTM32N) | EPSG:2154 (Lambert93) |
| Macro boundary | Borough (33) | Bezirk (12) | Arrondissement (20) |
| Meso boundary | MSOA (1011) | LOR Planungsraum (~450) | IRIS (~1000) |
| Population | Census 2021 (NOMIS TS001) | Zensus 2022 | INSEE Filosofi 2021 |
| Deprivation | IMD 2019 | Sozialatlas / Soziale Stadtentwicklung | INSEE Filosofi income deciles |
| Public greenspace | OS Open Greenspace | FIS-Broker Grünanlagen | IGN BD TOPO + APUR |
| Tree canopy (optional) | GLA i-Tree / Bluesky NTM | Berlin Senate Baumkataster | APUR canopy raster |

### 1.2 City manifest schema

Every city gets a YAML at `cities/<slug>.yaml` consumed by the dbt project, the Python pipeline, and the SPA. See `cities/london.yaml`.

```yaml
slug: london
name: London
country_iso: GB
language: en-GB
crs_equal_area: EPSG:27700
bbox_wgs84: [-0.51, 51.28, 0.33, 51.69]
centre_wgs84: [-0.1276, 51.5074]
levels:
  macro:  { code: borough, count: 33,   geometry: ons_borough }
  meso:   { code: msoa,    count: 1011, geometry: ons_msoa_2021 }
  micro:  { code: lsoa,    count: 4994, geometry: ons_lsoa_2021 }
sources:
  population:
    adapter: ons_nomis
    table: TS001
  deprivation:
    adapter: gov_uk_imd
    year: 2019
    field: income_decile
  public_greenspace:
    adapter: os_open_greenspace
    url: https://osdatahub.os.uk/downloads/open/OpenGreenspace
  imagery:
    stac: https://earth-search.aws.element84.com/v1/
    collection: sentinel-2-l2a
```

The pipeline reads each city's manifest and dispatches the right adapter. Adding a city is a YAML + a small adapter, not a fork.

## 2. Software architecture

### 2.1 Renderer stack

```
+------------------------------------------------------------------+
|  Next.js 16 (App Router, /app/[city]/page.tsx)                   |
|  +------------------------------------------------------------+  |
|  |  React (Zustand for UI, nuqs for URL state)               |  |
|  |  +------------------------------------------------------+  |  |
|  |  |  MapLibre GL JS  (basemap, labels, terrain, globe)  |  |  |
|  |  |    Layer order:                                      |  |  |
|  |  |      0  Basemap PMTiles vector                       |  |  |
|  |  |      1  3D buildings extrusion                       |  |  |
|  |  |   [-->] deck.gl interleaved here via MapboxOverlay  |  |  |
|  |  |      2  Roads                                        |  |  |
|  |  |   [-->] deck.gl interleaved (data overlays)         |  |  |
|  |  |      3  Labels                                       |  |  |
|  |  +------------------------------------------------------+  |  |
|  |  Web Worker:  DuckDB-Wasm + httpfs + spatial + raster     |  |
|  +------------------------------------------------------------+  |
+------------------------------------------------------------------+
```

### 2.2 MapLibre vs deck.gl — keep both

MapLibre is mature at: vector basemaps, label collision, sprites, terrain, globe, smooth pan/zoom, accessibility. Deck.gl is mature at: GPU-accelerated data layers, GLSL shaders, H3 hexagons, raster algebra, animation. Use both via `MapboxOverlay`:

```ts
import { MapboxOverlay } from '@deck.gl/mapbox'
const overlay = new MapboxOverlay({ interleaved: true, layers: [...] })
map.addControl(overlay)
```

`interleaved: true` lets data sit between MapLibre layers (data-over-roads-under-labels), which looks far better than a top overlay.

### 2.3 Layer composition

| Layer | Renderer | Source | Z-index |
|---|---|---|---|
| Basemap vector | MapLibre | `pmtiles://r2/basemap.pmtiles` | 0 |
| 3D buildings | MapLibre | basemap PMTiles `buildings` source-layer | 1 |
| NDVI raster | deck.gl-raster | COG via `RasterTileLayer` + `COGSource` | 2 |
| ΔNDVI raster | deck.gl-raster | COG, divergent ramp | 2 |
| MSOA / LSOA / IRIS / LOR | deck.gl `MVTLayer` | `pmtiles://r2/<city>/<level>.pmtiles` | 3 |
| H3 hex | deck.gl `H3HexagonLayer` | `parquet://r2/<city>/h3_res9.parquet` filtered by viewport bbox | 4 |
| Parks overlay | deck.gl `GeoJsonLayer` | DuckDB query on `parks_<city>.parquet` | 5 |
| Anomaly icons | deck.gl `IconLayer` | `anomalies.parquet` | 6 |
| Selection highlight | deck.gl `GeoJsonLayer` | client-side | 7 |

### 2.4 Frontend stack

- **Next.js 16** App Router; routes: `/[city]`, `/[city]/[level]`, `/[city]/about`, `/api/og`
- **Static export** per city; deploy to Vercel
- **Tailwind + shadcn/ui** primitives; brand tokens via `theme.config.ts` driving CSS custom properties + `tailwind.config.ts theme.extend`
- **State**: Zustand for ephemeral, **nuqs** for URL-synced (`?city=london&level=msoa&var=delta&t=2024&bbox=...`)
- **Data fetching**: React Query for STAC catalogue (stale-while-revalidate); DuckDB-Wasm queries memoised
- **Code-split**: deck.gl, MapLibre, DuckDB-Wasm, PMTiles all dynamic-imported; first paint = basemap only (~200 KB JS)
- **Observability**: Vercel Web Analytics + Sentry; Lighthouse CI on every PR

### 2.5 DuckDB-Wasm in the browser

```ts
// lib/duckdb/worker.ts
import * as duckdb from '@duckdb/duckdb-wasm'

export async function initDb() {
  const bundle = await duckdb.selectBundle(JSDELIVR_BUNDLES)
  const worker = new Worker(bundle.mainWorker!, { type: 'module' })
  const db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(), worker)
  await db.instantiate(bundle.mainModule)
  const conn = await db.connect()
  await conn.query("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
  // best-effort raster extension
  try { await conn.query("INSTALL raster FROM community; LOAD raster;") }
  catch (e) { console.warn('raster ext unavailable; falling back to pre-baked COGs', e) }
  return conn
}
```

Views over R2 parquet are registered once at startup; all subsequent queries are fast joins/filters.

## 3. The DuckDB raster extension changes the calculus

Until now, raster work was Python-only. The community `raster` extension exposes `RT_Read`, `RT_Cube*` arithmetic, `RT_CubeClip`, `RT_CubeStats`, `RT_Polygon`, `RT_GdalConfig` — all GDAL-backed. NDVI becomes a one-liner; zonal stats is a join.

```sql
-- NDVI in pure SQL, no Python
INSTALL raster FROM community; LOAD raster;
WITH bands AS (
  SELECT RT_Read('https://r2/.../band_late_B04.tif') AS red,
         RT_Read('https://r2/.../band_late_B08.tif') AS nir
)
SELECT RT_CubeDivide(
         RT_CubeSubtract(b.nir.cube, b.red.cube),
         RT_CubeAdd     (b.nir.cube, b.red.cube)
       ) AS ndvi_cube
FROM bands b;

-- Zonal stats per MSOA
SELECT
  m.MSOA21CD,
  RT_CubeStats(RT_CubeClip(ndvi_cube, m.geometry)).mean AS mean_ndvi
FROM msoas m
CROSS JOIN bands b;
```

### 3.1 Two execution modes, same SQL

| Mode | Where it runs | When |
|---|---|---|
| **Server-side** | dbt-duckdb in CI (GitHub Actions) | Pre-bake gold parquet for the SPA |
| **Browser-side** | DuckDB-Wasm Web Worker | Interactive raster algebra, custom thresholds, ad-hoc band ratios |

If the WASM build of `raster` is unavailable, the server still runs and the SPA reads pre-baked COGs only.

## 4. Data architecture (medallion)

### 4.1 Storage layout

```
r2://green-cities/
  bronze/                          # raw, immutable, append-only
    stac/{city}/{collection}/{date}.json
    sentinel2_cogs/...             # Element 84 mirror; we don't copy, just point
    overture/release=2026-04-15.0/...
    boundaries/{city}/{source}/{vintage}/
    population/{city}/{source}/{vintage}/
    deprivation/{city}/{source}/{vintage}/
    parks/{city}/{source}/{vintage}/
  silver/                          # cleaned, conformed, harmonised
    boundaries/{city}_{level}.parquet
    parks/{city}.parquet
    ndvi_annual/{city}/{year}.tif  # COG, equal-area CRS
  gold/                            # what the SPA reads
    {city}/msoa_attrs.parquet      # or iris_attrs / lor_attrs
    {city}/h3_res9.parquet
    {city}/h3_ndvi_timeseries.parquet
    {city}/anomalies.parquet
    {city}/lsoa_equity.parquet
    manifest.json                  # versioned dataset SHAs
  pmtiles/
    basemap.pmtiles
    {city}/{level}.pmtiles
  cogs/
    {city}/ndvi_{year}.tif
    {city}/ndvi_delta.tif
```

CORS is set on the bucket to allow the production origin and `localhost:3000`.

### 4.2 dbt-duckdb project

```
dbt/
  dbt_project.yml
  profiles.yml                    # uses ${R2_*} env vars
  models/
    staging/                      # materialized=view, source=bronze
      stg_stac_items.sql
      stg_overture_land_use.sql
      stg_msoa_2021.sql
      ...
    intermediate/                 # materialized=table, in silver
      int_msoa_clipped_27700.sql
      int_h3_polyfill_msoa.sql
      int_ndvi_zonal_msoa.sql     # uses RT_CubeClip + RT_CubeStats
      int_parks_unioned.sql
    marts/                        # materialized=external (parquet to R2)
      msoa_attrs.sql
      lsoa_equity.sql
      h3_res9.sql
      h3_ndvi_timeseries.sql
      anomalies.sql
  seeds/
    cities.csv                    # mirror of the manifest
  tests/
    not_null_msoa21cd.sql
    accepted_values_access_class.sql
    area_weighted_overlap_sums_to_one.sql
  macros/
    ndvi_zonal.sql                # parametrised by city + year
    h3_polyfill.sql
    angst_metrics.sql
```

### 4.3 Schema contracts (silver / gold)

```sql
-- silver.boundaries: harmonised across cities
city            VARCHAR
area_code       VARCHAR     -- MSOA21CD / iris_code / lor_code
area_name       VARCHAR
level           VARCHAR     -- borough | msoa | lsoa | iris | lor | bezirk | arrondissement
parent_code     VARCHAR     -- e.g. borough for MSOA
population      INTEGER
deprivation     INTEGER     -- decile, harmonised 1-10
geometry        GEOMETRY    -- in equal-area CRS

-- silver.parks
city            VARCHAR
source          VARCHAR     -- os_greenspace | osm | overture_lu | overture_lc
kind            VARCHAR     -- park | garden | allotment | wood | grass | ...
access_class    VARCHAR     -- public | restricted | cover
geometry        GEOMETRY

-- gold.h3_res9 (per city)
h3              UBIGINT
parent_r6       UBIGINT     -- for spatial pruning
area_code       VARCHAR
ndvi_2024       FLOAT
ndvi_delta      FLOAT
green_share     FLOAT
green_per_capita_m2 FLOAT
gi_star         FLOAT       -- Getis-Ord local
lisa_cluster    VARCHAR
```

### 4.4 STAC ingestion

```python
# pipeline/src/stac_ingest.py — pseudocode
from pystac_client import Client
def fetch(city: dict, year: int) -> list[Item]:
    cat = Client.open(city['sources']['imagery']['stac'])
    return list(cat.search(
        collections=[city['sources']['imagery']['collection']],
        bbox=city['bbox_wgs84'],
        datetime=f'{year}-06-01/{year}-08-31',
        query={'eo:cloud_cover': {'lt': 15}},
    ).items())
```

Items are written to `bronze/stac/{city}/{year}.json`; the dbt model `int_ndvi_annual` reads them with `read_json`, picks per-tile COG URLs, and runs `RT_Read` with `RT_GdalConfig('GDAL_HTTP_RANGE_REQUEST_SIZE', '65536')`.

## 5. Modelling pipeline

### 5.1 Two stages

1. **Baseline RandomForest** — predict mean NDVI from non-satellite features (pop_density, dist_to_centre, dist_to_park, area). Feature importances feed the methodology page.
2. **Hierarchical model** — borough random effects so residuals are interpretable as "given this borough's typical greenness, this MSOA is +X greener / -Y greyer". `pymc` or `bambi`.

### 5.2 Cross-city normalisation

Cities differ in mean density and absolute green; normalise features within each city via percentile rank before fitting if a single cross-city model is used. The default is one model per city.

### 5.3 Time-series tests

Per H3 cell: Sen's slope + Mann-Kendall significance, computed with `pymannkendall` once per pipeline run. Output to `gold/{city}/h3_trend.parquet`.

### 5.4 Spatial autocorrelation

`pysal`/`esda` Moran's I global + Getis-Ord Gi* local. Result columns added to `h3_res9.parquet`. LISA cluster type joined to anomalies.

### 5.5 Anomaly export

```
anomalies.parquet
  area_code         VARCHAR
  observed_ndvi     FLOAT
  predicted_ndvi    FLOAT
  residual          FLOAT
  residual_z        FLOAT
  lisa_cluster      VARCHAR    -- HH | LH | HL | LL | NS
  surprise_score    FLOAT      -- composite of residual_z + ANGSt deficit
```

### 5.6 Versioning

Every pipeline run emits `gold/manifest.json`:

```json
{
  "release": "2026-05-12",
  "datasets": { "msoa_attrs": "sha256:...", "h3_res9": "sha256:..." },
  "models":   { "rf_msoa_ndvi": "sha256:...", "version": "0.4.1" },
  "git":      { "commit": "abc123", "branch": "main" }
}
```

The SPA reads `manifest.json`; if a checksum mismatches the cached version, it cache-busts. If parsing fails, it falls back to the previous good manifest.

## 6. Orchestration

### 6.1 GitHub Actions (default)

`.github/workflows/build.yml`:

```yaml
on:
  schedule: [{ cron: '0 6 * * 1' }]      # weekly Monday 06:00 UTC
  workflow_dispatch:
    inputs:
      city:    { type: choice, options: [london, berlin, paris, all] }
      release: { type: string }
jobs:
  build:
    strategy:
      matrix: { city: [london, berlin, paris] }
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run python pipeline/run.py --city ${{ matrix.city }}
      - run: uv run dbt build --vars '{ "city": "${{ matrix.city }}" }'
      - run: uv run python pipeline/publish.py --city ${{ matrix.city }}
        env:
          R2_ACCESS_KEY_ID:     ${{ secrets.R2_ACCESS_KEY_ID }}
          R2_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_ACCESS_KEY }}
```

### 6.2 Heavy compute escape hatches

GitHub-hosted runners are ~7 GB RAM. If Sentinel-2 mosaic builds blow that:

1. Self-hosted runner on Hetzner CCX23 (~€20/month, 32 GB RAM).
2. GCP Batch / AWS Batch one-shot jobs invoked by the workflow.

### 6.3 Alternative orchestrators

Dagster Cloud or Prefect free tier if observability becomes important. Both have native dbt integrations.

## 7. Infrastructure-as-Code (Terraform)

```
infra/terraform/
  main.tf                  # backend = "remote" (Terraform Cloud)
  variables.tf
  outputs.tf
  modules/
    cloudflare_r2/
      main.tf              # bucket + CORS + lifecycle
    cloudflare_dns/
      main.tf              # tiles.green.cities, app.green.cities
    vercel_project/
      main.tf              # project + env vars + git integration
    cloud_run_optional/
      main.tf              # ee-proxy or titiler if needed
    github_actions_secrets/
      main.tf              # R2 keys, dbt profiles
```

Pinned providers: `cloudflare/cloudflare`, `vercel/vercel`, `integrations/github`, `hashicorp/google` (optional). State lives in Terraform Cloud free tier. CI runs `tflint` + `tfsec` on PRs.

Switch to OpenTofu (`opentofu/opentofu`) if HashiCorp licensing is a concern.

## 7a. Vercel Pro deployment

User has Vercel Pro on team `gerardoezequiel` (`team_vDeAFAr6tfJEEcvfxUavreth`). The plan changes a few decisions vs the default-tier write-up:

### What Vercel Pro buys us

- **Fluid Compute** (enabled by default for new projects since 2025-04-23): functions auto-scale, share warm execution, support up to 800 s `maxDuration` and 3 GB memory on Pro. This replaces the Cloud Run "ee-proxy" and lets us run a heavier raster / ML inference function natively.
- **Vercel Blob**: object storage with multipart upload (≥5 MB chunks). Public + private modes, native CDN, signed URLs. 100 GB included on Pro. Good for medium assets (PMTiles, small parquet) — but **keep large COGs and big parquet on Cloudflare R2** because R2 has zero egress fees and our biggest cost driver is bytes-served.
- **Edge Config**: tiny key-value store readable from edge runtime in <1 ms. Use for the city manifest registry, feature flags, brand-tokens lookup. NOT for large data.
- **Edge Network + ISR**: per-city static export with on-demand revalidation when the pipeline publishes a new gold manifest.
- **`@vercel/og`**: dynamic Open Graph cards (current map view) on Edge Runtime.
- **Speed Insights + Web Analytics**: included.
- **Concurrent builds**: matrix CI builds without queueing.

### Storage split

| Asset | Where | Why |
|---|---|---|
| COGs (NDVI, ΔNDVI, clusters, annual medians) | **R2** | Often 5–50 MB each; zero egress matters; R2 ≈ $0.015/GB-month |
| PMTiles (basemap, MSOA, LSOA, IRIS, LOR) | **R2** | Same reason; range-request friendly; static |
| Gold parquet (msoa_attrs, h3_res9, anomalies) | **R2** | DuckDB-Wasm reads via httpfs; range requests |
| Bronze parquet / raw STAC JSON | **R2** | Pipeline-only; cheap to keep around |
| Tiny JSON manifests, brand tokens | **Vercel Edge Config** | <1 ms reads at the edge |
| OG images | **Vercel Blob** (cached) | Generated by `@vercel/og` |
| User-uploaded annotations (later) | **Vercel Blob** (private) | Per-user signed URLs |

### Compute split

| Job | Where | Notes |
|---|---|---|
| Build pipeline (STAC → bronze → silver → gold) | **GitHub Actions** | Weekly cron, matrix per city; `dbt-duckdb` |
| On-demand zonal stats / ad-hoc raster algebra | **Vercel Function (Fluid)** | `runtime: 'nodejs'`, `maxDuration: 800`, calls duckdb-wasm or duckdb node addon |
| OG card generation | **Vercel Function (Edge)** | `@vercel/og` |
| STAC catalogue proxy + cache | **Vercel Function (Edge)** | `Cache-Control: s-maxage=86400` |
| `manifest.json` revalidation webhook | **Vercel Function (Edge)** | called from the GitHub Action; triggers ISR |
| ee-proxy (only if GEE Dynamic World wanted) | **Vercel Function (Node, Fluid)** | service-account auth |

### Vercel-specific config

`vercel.json`:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "fluid": true,
  "functions": {
    "app/api/zonal/*.ts":   { "memory": 3008, "maxDuration": 60 },
    "app/api/ee-proxy/*.ts":{ "memory": 1024, "maxDuration": 300 },
    "app/api/og/*.ts":      { "memory": 256,  "maxDuration": 10 }
  },
  "headers": [
    {
      "source": "/(.*)",
      "headers": [
        { "key": "Cross-Origin-Opener-Policy",   "value": "same-origin" },
        { "key": "Cross-Origin-Embedder-Policy", "value": "require-corp" }
      ]
    }
  ],
  "crons": [
    { "path": "/api/cron/refresh-stac", "schedule": "0 6 * * 1" }
  ]
}
```

The COOP/COEP headers are required for SharedArrayBuffer, which DuckDB-Wasm uses for multi-threaded reads.

### CLI workflow

```sh
# one-time
vercel link --project green-london --scope gerardoezequiel
vercel env pull .env.local
vercel env add R2_ACCESS_KEY_ID            production
vercel env add R2_SECRET_ACCESS_KEY        production
vercel env add NEXT_PUBLIC_R2_BUCKET_URL   production preview development
vercel blob create-store green-cities-blob --region fra1 --access public

# develop
vercel dev

# preview deploy on push (auto via git integration)
git push origin feat/city-berlin

# production
vercel --prod
```

Edge Config for the city registry:

```sh
vercel edge-config create green-cities-registry
# then push the manifest JSON
node -e "console.log(JSON.stringify(require('./cities/_index.json')))" \
  | vercel edge-config items put --store=ecfg_... --key=cities --value-stdin
```

### Updated Terraform module list

```
infra/terraform/modules/
  cloudflare_r2/         # COGs, PMTiles, large parquet
  cloudflare_dns/        # tiles.green.cities, app.green.cities
  vercel_project/        # green-london (and per-city projects later)
  vercel_blob_store/     # green-cities-blob
  vercel_edge_config/    # green-cities-registry
  vercel_env_vars/       # production + preview + development
  github_actions_secrets/
```

The `vercel_*` modules use the official `vercel/vercel` Terraform provider. Outputs from `cloudflare_r2` (bucket URL, access keys) feed `vercel_env_vars` so a single `terraform apply` configures both clouds.

### Deploy guard rails

- **Preview deploys** for every PR; data points at staging R2 prefix `r2://green-cities-staging/...`.
- **Production deploy** only from `main` after pipeline build green.
- **Skew protection**: Vercel default; the SPA loads the gold manifest on boot and refuses to render with a stale dataset SHA.
- **Password protection** on staging until launch (Pro feature).

## 8. Repository layout

```
green-cities/                       # single monorepo
  apps/
    web/                            # Next.js 16
      app/
        [city]/page.tsx
        [city]/[level]/page.tsx
        [city]/about/page.tsx
        api/og/route.ts
      components/{map,panels,ui}/
      lib/{duckdb,layers,state,theme}/
      cities/                       # symlinked from /cities
  cities/                           # YAML manifests
    london.yaml
    berlin.yaml
    paris.yaml
  dbt/                              # dbt-duckdb project
    dbt_project.yml
    models/{staging,intermediate,marts}/
    tests/  macros/  seeds/
  pipeline/                         # Python orchestration
    run.py                          # entrypoint
    src/{stac_ingest,publish,model,anomalies}.py
  infra/
    terraform/
    docker/                         # optional self-hosted runner
  queries/                          # browser-side SQL
    green_areas.sql
    timeseries.sql
    equity.sql
    raster_examples.sql             # NDVI in DuckDB-raster
  data-pipeline/                    # legacy Python scripts (will fold into pipeline/)
  docs/
    PLAN.md
    ARCHITECTURE.md  ← this file
  .github/workflows/
    build.yml                       # weekly + manual
    web.yml                         # Vercel preview on PR
    terraform.yml                   # plan on PR, apply on main
```

## 9. Cost ceiling (3 cities)

| Item | Provider | Cost |
|---|---|---|
| Object storage ~5 GB | Cloudflare R2 | ~$0.10 / month |
| Egress | Cloudflare R2 | $0 |
| DNS | Cloudflare | $0 |
| Frontend hosting | Vercel hobby | $0 |
| CI compute | GitHub Actions (public repo) | $0 |
| Terraform state | Terraform Cloud free | $0 |
| Sentry, Lighthouse CI | free tiers | $0 |
| **Total recurring** | | **< $5 / month** |

Optional: Cloud Run ee-proxy (~$5/month idle), Hetzner self-hosted runner (€20/month).

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| `raster` extension lacks WASM build | Server-side dbt-duckdb runs same SQL; SPA falls back to pre-baked COGs |
| Sentinel-2 phenology / atmospheric noise | Use June–August median composites; show uncertainty in methodology page |
| Cross-city schema drift | Manifest-driven adapters; dbt schema tests on silver |
| GitHub-hosted runner RAM | Self-hosted runner or GCP Batch escape hatch |
| MapLibre + deck.gl interleaving glitches | Pin both versions; visual regression tests via Playwright on a fixed bbox |
| CRS mistakes (area in 4326) | Lint rule: every `ST_Area` call in dbt requires `to_local_crs()` macro wrapper |
| Equity narrative misuse | Methodology page explicit about caveats; `prefers-reduced-motion` and AA contrast |

## 11. The 60-point reasoning trace

Steps 1-8: multi-city generalisation. Steps 9-16: software architecture (deck.gl + MapLibre via MapboxOverlay, Next.js static export, code-split). Steps 17-24: integrating the DuckDB raster extension. Steps 25-32: medallion data architecture with dbt-duckdb. Steps 33-40: two-stage modelling, cross-city normalisation, time-series + spatial autocorrelation. Steps 41-48: GitHub Actions orchestration + Terraform IaC. Steps 49-56: frontend stack, state, code-split, observability. Steps 57-60: cross-CRS pitfalls, ethics, cost ceiling, synthesis.

## 12. References

- DuckDB raster extension: <https://duckdb.org/community_extensions/extensions/raster>
- DuckDB 1.5.0: <https://duckdb.org/2026/03/09/announcing-duckdb-150.html>
- deck.gl MapboxOverlay: <https://deck.gl/docs/api-reference/mapbox/mapbox-overlay>
- deck.gl-raster: <https://github.com/developmentseed/deck.gl-raster>
- Earth Search STAC: <https://earth-search.aws.element84.com/v1/>
- Overture release 2026-04-15.0: <https://docs.overturemaps.org/blog/2026/04/15/release-notes/>
- dbt-duckdb: <https://github.com/duckdb/dbt-duckdb>
- PMTiles: <https://github.com/protomaps/PMTiles>
- INSEE IRIS: <https://www.insee.fr/fr/information/2017499>
- BKG Verwaltungsgebiete: <https://gdz.bkg.bund.de/>
- ANGSt: Natural England, *Nature Nearby* (2010)
