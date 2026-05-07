{{ config(materialized='external', format='parquet') }}

-- Gold: per-MSOA attribute table read by the SPA via DuckDB-Wasm.
-- Joins boundaries, population, deprivation, NDVI zonal stats, anomalies.

WITH boundaries AS (
  SELECT * FROM {{ ref('int_boundaries_clipped') }}
  WHERE level = 'msoa' AND city = '{{ var("city") }}'
),
ndvi AS (
  SELECT * FROM {{ ref('int_ndvi_zonal') }}
  WHERE city = '{{ var("city") }}'
),
parks AS (
  SELECT * FROM {{ ref('int_parks_per_area') }}
  WHERE city = '{{ var("city") }}' AND level = 'msoa'
),
anomalies AS (
  SELECT * FROM {{ ref('int_anomalies') }}
  WHERE city = '{{ var("city") }}' AND level = 'msoa'
)
SELECT
  b.area_code           AS MSOA21CD,
  b.area_name           AS MSOA21NM,
  b.parent_code         AS borough,
  b.population,
  b.area_km2,
  b.population / NULLIF(b.area_km2, 0) AS pop_density,
  b.deprivation         AS imd_income_decile,
  n.ndvi_2019,
  n.ndvi_2024,
  n.ndvi_delta,
  n.ndvi_std,
  n.prop_water,
  p.public_green_m2,
  p.private_green_m2,
  p.public_green_m2 / NULLIF(b.population, 0) AS green_per_capita_m2,
  p.dist_to_public_green_2ha_m,
  a.predicted_ndvi,
  a.residual_ndvi,
  a.residual_z,
  a.lisa_cluster,
  a.surprise_score,
  ST_AsWKB(b.geometry)  AS geometry_wkb
FROM boundaries b
LEFT JOIN ndvi      n USING (area_code)
LEFT JOIN parks     p USING (area_code)
LEFT JOIN anomalies a USING (area_code)
