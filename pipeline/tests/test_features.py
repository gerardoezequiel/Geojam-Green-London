import math

import geopandas as gpd
from shapely.geometry import box

from pipeline.src.features import FEATURE_COLUMNS, build_feature_frame


def test_feature_engineering_snapshot():
    gdf = gpd.GeoDataFrame(
        {
            "MSOA21CD": ["E1", "E2"],
            "MSOA21NM": ["Camden 001", "Barnet 002"],
            "pop_density": [99.0, 8.0],
            "dist_to_centre_km": [3.0, 12.0],
            "dist_to_park_km": [1.0, 2.0],
            "area_km2": [4.0, 16.0],
            "mean_ndvi_late": [0.2, 0.4],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="EPSG:4326",
    )
    out = build_feature_frame(gdf)
    assert list(out.columns) == ["MSOA21CD", "MSOA21NM", "mean_ndvi_late"] + FEATURE_COLUMNS
    assert str(out["MSOA21CD"].dtype) == "string"
    assert str(out["borough"].dtype) == "string"
    assert str(out["is_inner"].dtype) == "int64"
    assert math.isclose(out.loc[0, "log_pop_density"], math.log1p(99.0))
    assert out.loc[0, "dist_centre_sq"] == 9.0
    assert out.loc[0, "density_x_dist"] == 297.0
    assert out.loc[0, "park_access"] == 0.5
    assert out.loc[0, "is_inner"] == 1
    assert out.loc[1, "borough"] == "Barnet"

