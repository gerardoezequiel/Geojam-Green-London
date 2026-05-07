import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from pipeline.src.anomalies import ANOMALY_COLUMNS, build_anomalies


def _grid_gdf():
    boroughs = ["Camden", "Barnet", "Hackney", "Lambeth", "Merton"]
    rows = []
    geoms = []
    for i in range(15):
        x, y = i % 5, i // 5
        rows.append(
            {
                "MSOA21CD": f"E{i:08d}",
                "MSOA21NM": f"{boroughs[i % 5]} {i:03d}",
                "pop_density": 800 + i * 80,
                "dist_to_centre_km": 1.5 + x + y,
                "dist_to_park_km": 0.2 + 0.1 * x,
                "area_km2": 1.2 + 0.1 * y,
                "mean_ndvi_late": 0.15 + 0.01 * i,
            }
        )
        geoms.append(box(x, y, x + 1, y + 1))
    return gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")


def test_anomalies_parquet_schema(tmp_path):
    anomalies, _ = build_anomalies(_grid_gdf())
    path = tmp_path / "anomalies.parquet"
    anomalies.to_parquet(path, index=False)
    got = pd.read_parquet(path)
    assert list(got.columns) == ANOMALY_COLUMNS
    assert str(got["MSOA21CD"].dtype) == "string"
    assert str(got["lisa_cluster"].dtype) == "string"
    for col in [c for c in ANOMALY_COLUMNS if c not in {"MSOA21CD", "lisa_cluster"}]:
        assert str(got[col].dtype) == "float64"
    assert set(got["lisa_cluster"]).issubset({"HH", "HL", "LH", "LL", "NS"})

