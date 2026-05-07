{{ config(materialized='external', format='parquet') }}

SELECT
  MSOA21CD,
  predicted_ndvi,
  actual_ndvi,
  residual,
  residual_z,
  gi_star,
  gi_p,
  lisa_cluster,
  surprise_score
FROM read_parquet('assets/parquet/london/anomalies.parquet')

