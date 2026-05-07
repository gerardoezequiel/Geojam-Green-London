# Performance budget and tactics

Drawn from a Sonar deep-research pass and an architecture audit (May 2026). British English. No em dashes.

## 1. Verified facts that change the architecture

### DuckDB-Wasm in 2026

| Fact | Source |
|---|---|
| WASM bundle ~17 MB, ~6 MB gzipped | duckdb-wasm GitHub discussions |
| Cold start (parse + compile) ~700 ms on M2, ~2.5–4 s on mid-tier mobile | MotherDuck benchmarks Q3 2024 |
| Range requests on R2 with `httpfs_keep_alive` + `parquet_metadata_cache`: 500–800 ms second-query | duckdb 1.5 release notes |
| Spatial extension works in WASM. ST_Intersects, ST_Contains, ST_DWithin, ST_Area, ST_Buffer, ST_Union_Agg all OK | duckdb-spatial WASM build |
| **`raster` community extension does NOT compile to WASM**. GDAL is the blocker. | duckdb-wasm-extensions-ci docs |
| **H3 extension does NOT compile to WASM**. Use `h3-js`. | h3-duckdb#71 |
| SharedArrayBuffer + COOP/COEP gives 2–4x speedup on heavy ops; mobile single-threaded fallback is fine for typical interactions | duckdb-wasm#1922 |
| Mobile memory cap ~100–300 MB single-tab, hard kill on overflow | emscripten#19374 |
| 32-bit pointers cap WASM heap at 2 GB theoretically; practical desktop ceiling 500 MB–1 GB | duckdb-wasm#1241 |

### What this means for our plan

1. The `raster` extension stays on the **server side** in dbt-duckdb (CI). The browser reads pre-baked COGs and parquet only. Architecturally simpler, perf-equivalent for our payloads.
2. H3 cell maths in the browser uses `h3-js`. DuckDB-Wasm filters parquet by H3 strings or UBIGINTs.
3. We must self-host the DuckDB-Wasm bundle on R2 (one origin, immutable cache).

## 2. Performance budgets

| Metric | Target | Notes |
|---|---|---|
| TTI to basemap | <1.0 s on M2 fibre, <2.5 s on 4G | MapLibre + PMTiles only |
| TTI to first choropleth | <1.5 s on M2, <4 s on 4G | default variable baked into PMTiles |
| First NDVI raster paint | <2.5 s on M2, <6 s on 4G | one COG, single ramp |
| Variable change | <300 ms p95 | parquet range-fetch + GLSL ramp swap |
| Time slider tick | <250 ms p95 | sorted parquet + zone-map prune |
| Bundle (initial) | <250 KB JS gzipped | Map basemap only |
| Bundle (data layer chunk) | <600 KB gzipped | deck.gl + duckdb-wasm shim |
| Mobile working set | <200 MB heap | enforced via DuckDB memory_limit |

## 3. Top 5 latency risks (and what to do)

1. **DuckDB-Wasm cold-start on the critical path.**
   Defer worker init until first user interaction or 1500 ms idle. Self-host bundle on R2. Use `<link rel="modulepreload">` for the worker.

2. **COG range-request fan-out.**
   256x256 internal tiles, full overview pyramid (six levels for London 50 km width at 20 m), DEFLATE+PREDICTOR=2 (or ZSTD if loaders.gl supports it). Set `GDAL_HTTP_MERGE_CONSECUTIVE_RANGES=YES`.

3. **Bundle weight (MapLibre + deck.gl + duckdb-wasm).**
   Dynamic-import deck.gl after first MapLibre frame. Split `H3HexagonLayer` and `MVTLayer` into a separate chunk. Verify with bundle analyser.

4. **MVTLayer joining attribute parquet on first paint.**
   Bake the default variable into the PMTiles features so the first choropleth is geometry-only. Load the parquet on variable change.

5. **COOP/COEP header fragility.**
   `Cross-Origin-Embedder-Policy: require-corp` breaks the page if any third-party asset misses `Cross-Origin-Resource-Policy: cross-origin`. Serve everything from `tiles.green.cities` (R2 with explicit CORP), run a CORS smoke test in CI.

## 4. The three Phase-0/1 commitments

| # | Commit | Effort | Impact |
|---|---|---|---|
| 1 | Self-host DuckDB-Wasm bundle + extensions on R2 with immutable cache and `modulepreload` | 0.5 d | -1 to -3 s cold start on 4G |
| 2 | Sort + row-group every gold parquet (`ORDER BY parent_r6, h3, year`, ROW_GROUP_SIZE 50000), CI test on `parquet_metadata` | 1 d | 5-10x reduction in bytes-per-interaction |
| 3 | Bake default variable into MSOA/LSOA PMTiles; load parquet only on variable change | 1 d | DuckDB off the first-paint critical path |

Total: ~2.5 days. Reversible, testable, no lock-in.

## 5. Storage decision (post-research)

Confirmed: **Cloudflare R2 for all static assets**. Pricing reality:

| Provider | Storage | Egress | Pain points for our use |
|---|---|---|---|
| Cloudflare R2 | $0.015 / GB-month | $0 (zero egress) | none |
| Vercel Blob | included on Pro | included | 500 MB per-file limit |
| Supabase Storage (free) | 1 GB cap | **50 GB / month cap** | egress cap kills static-asset serving; 7-day inactivity pause; 1 concurrent DB connection |

Supabase free-tier egress is the killer. A single user pulling 500 MB of map assets is 1% of the monthly cap. R2 wins by two orders of magnitude.

## 6. The Supabase question

Defer until v2. Add only when we ship saved views, annotations, or auth. Then use the **Auth-only hybrid**: R2 for static data (unchanged), Supabase Auth for identity, Supabase Postgres for user metadata (saved views ~2 KB each, annotations ~1 KB). Free tier is sufficient for the user-data layer; the app keeps reading static assets from R2.

Schema sketch:

```sql
CREATE TABLE saved_views (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  city VARCHAR(32),
  state JSONB,           -- viewport, layer config, variable
  created_at TIMESTAMPTZ DEFAULT now()
);
ALTER TABLE saved_views ENABLE ROW LEVEL SECURITY;
CREATE POLICY own ON saved_views FOR ALL USING (auth.uid() = user_id);
```

## 6a. CLI ops with wrangler

Wrangler 4.81+ is the official Cloudflare CLI; it is already authenticated on this machine against account `9c004c6544357bb17253cbb463beb243`. Use it directly for all R2 ops instead of the S3-compatible shim. R2 SQL queries run in the dashboard or via the new `wrangler r2 object query` flow.

### One-time setup

```sh
# Create the bucket(s) and worker binding
wrangler r2 bucket create green-cities
wrangler r2 bucket create green-cities-staging

# Configure CORS to allow Range + production + localhost
cat > cors.json <<'JSON'
{
  "CORSRules": [{
    "AllowedOrigins": ["https://green.cities", "https://*.vercel.app", "http://localhost:3000"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["Range", "Content-Type", "If-Modified-Since"],
    "ExposeHeaders": ["Content-Range", "Content-Length", "ETag"],
    "MaxAgeSeconds": 86400
  }]
}
JSON
wrangler r2 bucket cors put green-cities --rules ./cors.json
wrangler r2 bucket dev-url enable green-cities          # for staging
wrangler r2 bucket domain add green-cities tiles.green.cities --zone-id <ZONE>

# DuckDB-Wasm bundle: self-host (point #1 from the perf wins above)
wrangler r2 object put green-cities/v1/duckdb/duckdb-eh.wasm \
  --file=node_modules/@duckdb/duckdb-wasm/dist/duckdb-eh.wasm \
  --content-type application/wasm \
  --cache-control "public, max-age=31536000, immutable"
wrangler r2 object put green-cities/v1/duckdb/duckdb-browser-eh.worker.js \
  --file=node_modules/@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js \
  --content-type application/javascript \
  --cache-control "public, max-age=31536000, immutable"
```

### Pipeline publish step

```sh
# Bulk upload gold/cogs/pmtiles to R2 from a CI runner
wrangler r2 object put green-cities/v1/pmtiles/london/msoa.pmtiles --file=$ASSETS/pmtiles/msoa.pmtiles
wrangler r2 object put green-cities/v1/cogs/london/ndvi_2024.tif --file=$ASSETS/cogs/ndvi_2024.tif
wrangler r2 object put green-cities/v1/parquet/london/h3_res9.parquet --file=$ASSETS/parquet/h3_res9.parquet
```

### Worker binding for advanced cases

For private buckets or signed URLs, bind R2 to a Cloudflare Worker via `wrangler.toml`:

```toml
name = "green-cities-edge"
main = "src/index.ts"
compatibility_date = "2026-05-07"

[[r2_buckets]]
binding = "TILES"
bucket_name = "green-cities"
preview_bucket_name = "green-cities-staging"
```

Then `env.TILES.get(...)`, `env.TILES.head(...)` from the worker. We won't need this for v1 (R2 public dev domain + custom domain is sufficient), but it is the path for v2 if we add private user uploads.

### Permissions for CI

For GitHub Actions, mint a scoped API token (R2 read+write on `green-cities` only) and set `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` as repo secrets. Wrangler is non-interactive when both env vars are set.

### Why wrangler over the S3 SDK

- Native to R2 — no signing dance, no endpoint config
- Same auth as the rest of the Cloudflare stack (DNS, Workers, Pages)
- First-class CORS, domain, lifecycle commands
- Worker binding gets us edge compute on the same data without copying

We still keep an S3-compatible endpoint in `dbt/profiles.yml` for `dbt-duckdb` to read parquet via `httpfs` (DuckDB only speaks S3). That is the only place the S3 shim is needed.

## 6b. Compute: GitHub Actions vs Hetzner — actual numbers

After verifying the existing Hetzner box and GitHub Actions tier, the recommendation is the inverse of the initial design. The repo is **public**, so GitHub Actions is free and sufficient for v1.

### Your Hetzner box `infra-01` (verified May 2026)

| Spec | Value |
|---|---|
| Type | CX33 (shared vCPU, AMD EPYC-Rome) |
| vCPU / RAM / Disk | 4 / 8 GB / 80 GB local SSD |
| Location | nbg1 (Nuremberg) |
| Included traffic | 20 TB / month |
| Monthly cost | **€7.79 (sunk)** |
| Disk free | 40 GB (32 GB used by ollama, karakeep, meilisearch, openclaw, etc.) |
| RAM free under load | ~5 GB |

### GitHub Actions tier (verified)

| Plan | Standard ubuntu-latest |
|---|---|
| Public repos | **Free, unlimited** |
| Private repos (Pro) | 3000 min/month included; $0.008/min after |
| Standard runner spec | 2 vCPU, 7 GB RAM, 14 GB SSD |
| Job cap | 6 hours |

The Green Cities repo is public, so v1 build cost on GH Actions is **€0**.

### Decision: GitHub Actions is the default; Hetzner is the escape hatch

| Job | Runner | Cost |
|---|---|---|
| Weekly pipeline build (3 cities × 9 years) | GitHub Actions `ubuntu-latest` | €0 |
| Frontend build + deploy | Vercel | included in Pro |
| Static asset serving | R2 | ~€0.05–0.50/mo |
| Heavy reprocessing, ML retraining, full-history rebuilds | **Hetzner infra-01 (self-hosted runner)** | €0 marginal |
| Bronze cache (optional) | Hetzner + Volume €0.40/mo per 100 GB | €0–4/mo |

### When to flip to Hetzner

- A single dbt-duckdb model OOMs above 6 GB working set (probably never at our scale)
- A job exceeds the 6-hour cap
- We move the repo private and burn through the 3000-min Pro budget
- ML training picks up (multiple Sentinel-2 years × multiple cities + spatial autocorrelation)

### Hetzner setup when needed

```sh
# On infra-01
mkdir actions-runner && cd actions-runner
curl -O -L https://github.com/actions/runner/releases/latest/download/actions-runner-linux-x64.tar.gz
tar xzf actions-runner-linux-x64.tar.gz
./config.sh \
  --url https://github.com/gerardoezequiel/Geojam-Green-London \
  --token <REGISTRATION_TOKEN> \
  --labels self-hosted,linux,hetzner,geo
sudo ./svc.sh install && sudo ./svc.sh start
```

Then in `.github/workflows/build.yml` switch only the heavy job:

```yaml
jobs:
  pipeline:
    runs-on: ${{ inputs.heavy && '[self-hosted, hetzner, geo]' || 'ubuntu-latest' }}
```

### Disk pressure on infra-01

40 GB free is borderline if we cache bronze data. Calculation:

| Item | Size |
|---|---|
| Bronze STAC items (3 cities × 9 years JSON) | ~50 MB |
| Bronze Overture clipped parquet | ~500 MB |
| Bronze Sentinel-2 COG metadata only (URLs) | ~10 MB |
| Working dbt-duckdb files | ~5 GB peak |
| Gold outputs (transient) | ~2 GB |
| **Total during build** | **~8 GB** |

Fits, but tight alongside ollama and karakeep. If we want a permanent bronze cache, attach a **Hetzner Volume** at €4/TB/month = €0.40 for 100 GB. Mount at `/mnt/bronze`.

### What never moves to Hetzner

- Static asset serving — R2 wins on egress and CDN reach
- Frontend hosting — Vercel wins on DX and edge
- Auth (when added) — Supabase free tier or Vercel Functions

### Why not a Pro plan to get a bigger GH runner

GitHub Actions has paid larger runners (4 vCPU/16 GB) at $0.016/min. A 30-min weekly build = $0.48/month. Cheap, but Hetzner already exists and a self-hosted runner is more portable. Use larger GH runners only if Hetzner is unavailable or we want zero-maintenance burst capacity.

## 7. Smoke tests in CI

- `parquet_metadata.sql` asserts row groups + sort order on every gold parquet
- Lighthouse CI budget on every PR (LCP <2.5 s on 4G profile, JS <250 KB initial)
- Playwright visual regression on basemap + choropleth at `dpr=2`
- CORS check: HEAD on every R2 path returns `cross-origin` CORP and `Range` allowed
