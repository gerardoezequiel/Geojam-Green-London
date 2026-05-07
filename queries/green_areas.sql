-- Green London — multi-source green-areas definition
-- Target: DuckDB / DuckDB-Wasm with httpfs + spatial extensions.
-- Replaces the BigQuery-flavoured original. See PLAN.md section 2 for rationale.

INSTALL httpfs;  LOAD httpfs;
INSTALL spatial; LOAD spatial;
SET s3_region = 'us-west-2';

-- Pin the Overture release. Bump intentionally; do not float.
SET VARIABLE overture_release = '2026-04-15.0';

-- 1. London polygon: union of 33 boroughs from Overture divisions.
CREATE OR REPLACE TABLE london_city AS
WITH boroughs AS (
  SELECT names.primary AS borough, geometry, bbox
  FROM read_parquet(
    's3://overturemaps-us-west-2/release/' || getvariable('overture_release')
    || '/theme=divisions/type=division_area/*.parquet',
    hive_partitioning = 1
  )
  WHERE country = 'GB'
    AND subtype = 'county'
    AND is_territorial
    AND names.primary IN (
      'Barking and Dagenham','Barnet','Bexley','Brent','Bromley',
      'Camden','Croydon','Ealing','Enfield','Greenwich','Hackney',
      'Hammersmith and Fulham','Haringey','Harrow','Havering',
      'Hillingdon','Hounslow','Islington','Kensington and Chelsea',
      'Kingston upon Thames','Lambeth','Lewisham','Merton','Newham',
      'Redbridge','Richmond upon Thames','Southwark','Sutton',
      'Tower Hamlets','Waltham Forest','Wandsworth','Westminster','City of London'
    )
)
SELECT
  'London' AS city,
  ST_MakeValid(ST_Union_Agg(geometry)) AS geom,
  MIN(bbox.xmin) AS xmin, MAX(bbox.xmax) AS xmax,
  MIN(bbox.ymin) AS ymin, MAX(bbox.ymax) AS ymax
FROM boroughs;

-- 2. Land-use green polygons (Overture). Bbox prefilter to skip row groups.
CREATE OR REPLACE TABLE overture_green_lu AS
SELECT
  l.id,
  l.subtype,
  l.class,
  l.names.primary AS name,
  l.geometry
FROM read_parquet(
  's3://overturemaps-us-west-2/release/' || getvariable('overture_release')
  || '/theme=land_use/type=land_use/*.parquet',
  hive_partitioning = 1
) l
JOIN london_city c ON
      l.bbox.xmax >= c.xmin AND l.bbox.xmin <= c.xmax
  AND l.bbox.ymax >= c.ymin AND l.bbox.ymin <= c.ymax
WHERE l.subtype IN (
    'park','village_green','dog_park','nature_reserve','national_park',
    'recreation_ground','playground','garden','allotments',
    'cemetery','golf_course','pitch','meadow','grass','forest','farmland','orchard'
  )
  AND ST_Intersects(l.geometry, c.geom);

-- 3. Land cover (raster-derived; complementary to land_use).
CREATE OR REPLACE TABLE overture_green_lc AS
SELECT
  lc.id,
  lc.subtype AS class,
  lc.geometry
FROM read_parquet(
  's3://overturemaps-us-west-2/release/' || getvariable('overture_release')
  || '/theme=base/type=land_cover/*.parquet',
  hive_partitioning = 1
) lc
JOIN london_city c ON
      lc.bbox.xmax >= c.xmin AND lc.bbox.xmin <= c.xmax
  AND lc.bbox.ymax >= c.ymin AND lc.bbox.ymin <= c.ymax
WHERE lc.subtype IN ('tree','grass','shrub','wetland')
  AND ST_Intersects(lc.geometry, c.geom);

-- 4. Unified green coverage with provenance and access class.
CREATE OR REPLACE TABLE london_green AS
WITH unioned AS (
  SELECT id, subtype AS kind, 'land_use' AS source, geometry
  FROM overture_green_lu
  UNION ALL
  SELECT id, class AS kind, 'land_cover' AS source, geometry
  FROM overture_green_lc
)
SELECT
  id,
  kind,
  source,
  ST_MakeValid(geometry) AS geom,
  CASE
    WHEN kind IN ('park','village_green','nature_reserve','national_park',
                  'recreation_ground','playground','dog_park','allotments')
      THEN 'public'
    WHEN kind IN ('garden','golf_course','pitch','farmland','orchard','cemetery')
      THEN 'restricted'
    ELSE 'cover'
  END AS access_class
FROM unioned;

-- 5. Per-borough green-area share, area-weighted.
CREATE OR REPLACE TABLE borough_green_share AS
SELECT
  b.borough,
  SUM(ST_Area(ST_Intersection(g.geom, b.geometry))) AS green_m2,
  ST_Area(b.geometry)                                AS borough_m2,
  SUM(ST_Area(ST_Intersection(g.geom, b.geometry)))
    / NULLIF(ST_Area(b.geometry), 0)                 AS green_share
FROM london_city_boroughs b   -- materialise from london_city CTE if needed
JOIN london_green g
  ON ST_Intersects(g.geom, b.geometry)
GROUP BY b.borough, b.geometry;

-- 6. Per-MSOA accessible green-space metrics (ANGSt-style).
-- Assumes msoa_attrs.parquet has population and geometry available locally.
CREATE OR REPLACE TABLE msoa_angst AS
WITH public_green_2ha AS (
  SELECT geom
  FROM london_green
  WHERE access_class = 'public'
    AND ST_Area(geom) >= 20000   -- ~2 ha in EPSG:27700 metres
)
SELECT
  m.MSOA21CD,
  m.population,
  MIN(ST_Distance(ST_Centroid(m.geometry), p.geom))
    AS dist_to_public_green_2ha_m,
  SUM(ST_Area(ST_Intersection(p.geom, m.geometry)))
    AS msoa_public_green_m2,
  SUM(ST_Area(ST_Intersection(p.geom, m.geometry)))
    / NULLIF(m.population, 0)    AS public_green_per_capita_m2
FROM read_parquet('s3://r2/green-london/v1/msoa.parquet') m
JOIN public_green_2ha p ON ST_DWithin(m.geometry, p.geom, 5000)
GROUP BY m.MSOA21CD, m.population, m.geometry;
