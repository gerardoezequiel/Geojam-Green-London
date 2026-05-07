{# Macro: ndvi_zonal — compute mean NDVI per polygon using the duckdb raster extension. #}
{# Args: red_url, nir_url, polygons_ref (must expose area_code, geometry in equal-area CRS). #}

{% macro ndvi_zonal(red_url, nir_url, polygons_ref) %}

WITH bands AS (
  SELECT
    RT_Read('{{ red_url }}') AS red,
    RT_Read('{{ nir_url }}') AS nir
),
ndvi_cube AS (
  SELECT
    RT_CubeDivide(
      RT_CubeSubtract(b.nir.cube, b.red.cube),
      RT_CubeAdd     (b.nir.cube, b.red.cube)
    ) AS cube
  FROM bands b
)
SELECT
  p.area_code,
  RT_CubeStats(RT_CubeClip(c.cube, p.geometry)).mean   AS ndvi_mean,
  RT_CubeStats(RT_CubeClip(c.cube, p.geometry)).stddev AS ndvi_std,
  RT_CubeStats(RT_CubeClip(c.cube, p.geometry)).min    AS ndvi_min,
  RT_CubeStats(RT_CubeClip(c.cube, p.geometry)).max    AS ndvi_max
FROM {{ polygons_ref }} p
CROSS JOIN ndvi_cube c

{% endmacro %}
