-- Multi-temporal NDVI time series via Earth Search STAC + AWS Open Data COGs.
-- DuckDB-Wasm cannot run a STAC search itself, so this query operates on a
-- pre-baked Parquet (data-pipeline/src/timeseries.py) keyed on H3 res-9 + year.

INSTALL httpfs; LOAD httpfs;

-- 1. Per-H3-cell NDVI trajectory 2017-2025 (June-August median per year).
CREATE OR REPLACE VIEW h3_ndvi_timeseries AS
SELECT
  h3,
  year,
  ndvi_median,
  n_scenes,
  -- year-on-year delta and rolling mean
  ndvi_median - LAG(ndvi_median) OVER (PARTITION BY h3 ORDER BY year) AS yoy_delta,
  AVG(ndvi_median) OVER (
    PARTITION BY h3 ORDER BY year
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
  ) AS ndvi_3yr_mean
FROM read_parquet('https://tiles.green.london/v1/parquet/h3_ndvi_timeseries.parquet');

-- 2. Linear trend slope (Sen's slope approximation) per H3 cell, last 9 years.
CREATE OR REPLACE TABLE h3_trend AS
SELECT
  h3,
  REGR_SLOPE(ndvi_median, year)         AS slope_per_year,
  REGR_R2(ndvi_median, year)            AS r2,
  COUNT(*)                              AS n_years,
  MIN(ndvi_median)                      AS ndvi_min,
  MAX(ndvi_median)                      AS ndvi_max
FROM h3_ndvi_timeseries
GROUP BY h3
HAVING COUNT(*) >= 5;

-- 3. Aggregate to MSOA for the choropleth time slider.
CREATE OR REPLACE TABLE msoa_trend AS
SELECT
  m.MSOA21CD,
  AVG(t.slope_per_year)         AS mean_slope,
  STDDEV(t.slope_per_year)      AS slope_sd,
  AVG(t.r2)                     AS mean_r2
FROM h3_trend t
JOIN read_parquet('https://tiles.green.london/v1/parquet/msoa_h3_lookup.parquet') l
  ON t.h3 = l.h3
JOIN read_parquet('https://tiles.green.london/v1/parquet/msoa_attrs.parquet') m
  ON l.MSOA21CD = m.MSOA21CD
GROUP BY m.MSOA21CD;
