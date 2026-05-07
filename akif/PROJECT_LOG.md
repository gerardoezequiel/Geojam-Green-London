# Geojam-Green-London: Project Log

## 1. Project Initialization (2026-05-07)
*   **Action:** Cloned repository `https://github.com/gerardoezequiel/Geojam-Green-London.git` to Desktop.
*   **Action:** Environment setup. Installed spatial libraries (`geopandas`, `rasterio`, `pystac-client`, `osmnx`, `stackstac`, `planetary-computer`).

## 2. Data Generation
*   **Action:** Executed `Data Prep notebooks/geojam-data-prep.ipynb` to generate the baseline 2019/2024 London dataset.
*   **Output:** Created `geojam_data/` directory containing Sentinel-2 bands, MSOA boundaries, and pre-computed NDVI rasters.

## 3. Annual Time Series (2015–2025)
*   **Goal:** Fetch clear-sky summer imagery for every year since the Sentinel-2 mission began.
*   **Method:**
    *   Search window: April 1st to October 31st (Extended growing season).
    *   Criteria: Strict >98% London coverage and target <0.1% cloud cover.
*   **Output:** Generated `sentinel_time_series/` containing annual `.npy` NDVI rasters.

## 4. Advanced Analytics & Metrics
*   **Goal:** Provide rich backend data for DuckDB + DeckGL front-end.
*   **Action:** Computed annual mean NDVI per MSOA for the entire 2015-2025 period.
*   **Action:** Derived land-cover proportions (`prop_water`, `prop_vegetation`, `prop_built_soil`) using spectral thresholding.
*   **Action:** Calculated Environmental Equity: `green_sqm_per_person`.
*   **Data Correction:** Identified and fixed a Census data error. Re-fetched 2021 Census "Total Usual Residents" to ensure accurate density and equity metrics.
*   **Output:** `advanced_analysis/msoa_advanced_metrics.csv` and `.gpkg`.

## 5. Sub-MSOA Analysis
*   **Goal:** Cluster pixel-level spectral data to identify "types" of greenness within neighbourhoods.
*   **Action:** Performed `MiniBatchKMeans` clustering on 6.6 million pixels using 4-band spectral data.
*   **Refinement:** Switched to a robust Rule-Based classification (NDVI + NDWI) to ensure accurate detection of the Thames and urban features.
*   **Output:** `advanced_analysis/land_cover_clusters.npy`.

## 6. Time Series Refinement (2016–2025)
*   **Action:** Removed 2015 data due to low data quality and sensor artifacts.
*   **Deep Patching:** Implemented an automated multi-scene stitching algorithm for the entire 2016-2025 period.
*   **Methodology Alignment:** Re-downloaded spectral bands (Green and NIR) for all years to enable NDWI-based water detection across the full series.
*   **Output:** Generated 10 high-fidelity annual land-cover maps in `annual_verification_maps/`. All maps are 100% complete with no edge artifacts.

--- Environmental Equity Analysis ---

TOP 5 MSOAs (Most Green per Person):
           MSOA21NM  green_sqm_per_person  population
932   Brentwood 001           4845.438590        9866
933   Brentwood 002           4392.732883        6364
940   Brentwood 009           3379.076657        6183
948     Bromley 042           3310.073950        6782
494  Hillingdon 031           2721.425009        7535

BOTTOM 5 MSOAs (Least Green per Person):
              MSOA21NM  green_sqm_per_person  population
912    Westminster 005             41.747563       12142
916    Westminster 009             42.316562       14478
835  Tower Hamlets 021             42.723113       12769
929    Westminster 022             44.121107        8271
969      Greenwich 035             44.629428       12093
