-- Equity lens: greenness × population × income deprivation.
-- All three sources pre-baked to R2; runtime DuckDB-Wasm joins.

INSTALL httpfs; LOAD httpfs;

-- 1. LSOA equity table (already has population + IMD income decile baked in).
CREATE OR REPLACE VIEW lsoa_equity AS
SELECT *
FROM read_parquet('https://tiles.green.london/v1/parquet/lsoa_equity.parquet');

-- 2. Borough roll-up: average accessible green per capita by income decile.
CREATE OR REPLACE TABLE borough_equity AS
SELECT
  borough,
  imd_income_decile,
  COUNT(*)                            AS lsoa_count,
  SUM(population)                     AS pop_total,
  SUM(public_green_m2)                AS green_total_m2,
  SUM(public_green_m2)
    / NULLIF(SUM(population), 0)      AS green_per_capita_m2,
  AVG(prop_pop_within_400m_public_green) AS access_400m_share,
  AVG(angst_compliant_2ha_300m::INT)  AS angst_compliant_share
FROM lsoa_equity
GROUP BY borough, imd_income_decile;

-- 3. Inequality slope: Spearman rank correlation between income decile
-- and green-per-capita. Negative slope = poorer areas have less green.
CREATE OR REPLACE TABLE london_equity_summary AS
SELECT
  CORR(imd_income_decile, green_per_capita_m2)         AS pearson_r,
  REGR_SLOPE(green_per_capita_m2, imd_income_decile)   AS slope,
  REGR_R2(green_per_capita_m2, imd_income_decile)      AS r2,
  COUNT(*)                                             AS n_lsoas
FROM lsoa_equity;

-- 4. Surprise index per MSOA: residual from population-density model
--    plus ANGSt deficit. The actionable map.
CREATE OR REPLACE VIEW msoa_surprise AS
SELECT
  m.MSOA21CD,
  m.MSOA21NM,
  a.residual_ndvi,                          -- from anomalies.parquet
  a.predicted_ndvi,
  a.actual_ndvi,
  e.green_per_capita_m2,
  e.angst_compliant_share,
  -- standardised composite
  (-1.0 * (a.residual_ndvi / NULLIF(a.residual_sd, 0)))
    + (1.0 - LEAST(e.angst_compliant_share, 1.0))      AS surprise_score
FROM read_parquet('https://tiles.green.london/v1/parquet/anomalies.parquet') a
JOIN read_parquet('https://tiles.green.london/v1/parquet/msoa_attrs.parquet') m
  USING (MSOA21CD)
LEFT JOIN (
  SELECT MSOA21CD,
         AVG(green_per_capita_m2)        AS green_per_capita_m2,
         AVG(angst_compliant_2ha_300m::INT) AS angst_compliant_share
  FROM lsoa_equity
  GROUP BY MSOA21CD
) e USING (MSOA21CD)
ORDER BY surprise_score DESC;
