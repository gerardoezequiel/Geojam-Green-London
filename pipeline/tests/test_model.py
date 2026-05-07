import geopandas as gpd
from shapely.geometry import box

from pipeline.src.features import build_feature_frame
from pipeline.src.model import train_predict


def _sample_gdf(n=20):
    names = ["Camden", "Barnet", "Hackney", "Lambeth", "Merton"]
    rows = []
    geoms = []
    for i in range(n):
        borough = names[i % len(names)]
        rows.append(
            {
                "MSOA21CD": f"E{i:08d}",
                "MSOA21NM": f"{borough} {i:03d}",
                "pop_density": 1000 + i * 50,
                "dist_to_centre_km": 2 + (i % 10),
                "dist_to_park_km": 0.1 + (i % 4) * 0.2,
                "area_km2": 1.0 + (i % 5) * 0.3,
                "mean_ndvi_late": 0.18 + (i % 7) * 0.025,
            }
        )
        geoms.append(box(i, 0, i + 1, 1))
    return gpd.GeoDataFrame(rows, geometry=geoms, crs="EPSG:4326")


def test_model_train_then_predict_shape(tmp_path):
    features = build_feature_frame(_sample_gdf())
    result = train_predict(features, tmp_path / "rf.pkl")
    assert len(result.predictions) == len(features)
    assert set(result.predictions.columns) == {
        "MSOA21CD",
        "predicted_ndvi",
        "actual_ndvi",
        "residual",
        "residual_z",
    }
    assert result.feature_importances["importance"].sum() > 0.99
    assert (tmp_path / "rf.pkl").exists()

