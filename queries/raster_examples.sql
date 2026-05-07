-- DuckDB raster extension — runtime examples for the SPA inspector and dbt.
-- Works in both server-side dbt-duckdb (CI) and DuckDB-Wasm (browser, when
-- the WASM build of the community extension is available).

INSTALL httpfs;  LOAD httpfs;
INSTALL spatial; LOAD spatial;
INSTALL raster FROM community; LOAD raster;

-- 1. NDVI on the fly from any two band COGs.
WITH bands AS (
  SELECT
    RT_Read('https://tiles.green.cities/london/cogs/band_late_B04.tif') AS red,
    RT_Read('https://tiles.green.cities/london/cogs/band_late_B08.tif') AS nir
)
SELECT
  RT_CubeDivide(
    RT_CubeSubtract(b.nir.cube, b.red.cube),
    RT_CubeAdd     (b.nir.cube, b.red.cube)
  ) AS ndvi_cube
FROM bands b;

-- 2. Per-MSOA mean NDVI by joining a polygon table to a raster.
CREATE OR REPLACE TABLE msoa_ndvi_late AS
WITH bands AS (
  SELECT
    RT_Read('https://tiles.green.cities/london/cogs/band_late_B04.tif') AS red,
    RT_Read('https://tiles.green.cities/london/cogs/band_late_B08.tif') AS nir
),
ndvi AS (
  SELECT RT_CubeDivide(
           RT_CubeSubtract(nir.cube, red.cube),
           RT_CubeAdd     (nir.cube, red.cube)
         ) AS cube
  FROM bands
)
SELECT
  m.MSOA21CD,
  RT_CubeStats(RT_CubeClip(n.cube, m.geometry)).mean   AS ndvi_mean,
  RT_CubeStats(RT_CubeClip(n.cube, m.geometry)).stddev AS ndvi_std
FROM read_parquet('https://tiles.green.cities/london/parquet/msoa_attrs.parquet') m
CROSS JOIN ndvi n;

-- 3. Threshold filtering: where is NDVI above 0.6 (canopy proxy)?
WITH ndvi AS (
  SELECT RT_Read('https://tiles.green.cities/london/cogs/ndvi_2024.tif').cube AS cube
)
SELECT
  RT_Polygon(RT_CubeGreaterEqual(n.cube, 0.6)) AS canopy_polygon
FROM ndvi n;

-- 4. Change detection between two NDVI rasters (interactive in the browser).
WITH a AS (SELECT RT_Read('.../ndvi_2019.tif').cube AS c),
     b AS (SELECT RT_Read('.../ndvi_2024.tif').cube AS c)
SELECT RT_CubeSubtract(b.c, a.c) AS delta_cube FROM a, b;

-- 5. Custom band ratio (NDWI for water).
WITH bands AS (
  SELECT
    RT_Read('.../band_late_B03.tif') AS green,
    RT_Read('.../band_late_B08.tif') AS nir
)
SELECT
  RT_CubeDivide(
    RT_CubeSubtract(b.green.cube, b.nir.cube),
    RT_CubeAdd     (b.green.cube, b.nir.cube)
  ) AS ndwi_cube
FROM bands b;
