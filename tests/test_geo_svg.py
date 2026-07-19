import geopandas as gpd
from shapely.geometry import Polygon

from tn_dashboard.geo.svg import VIEWBOX_H, VIEWBOX_W, region_svg_paths


def test_region_svg_paths_projects_into_viewbox():
    square = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    gdf = gpd.GeoDataFrame({"name": ["A"]}, geometry=[square])

    paths = region_svg_paths(gdf, name_column="name", simplify_tolerance=0.001)

    assert set(paths) == {"A"}
    d = paths["A"]
    assert d.startswith("M ") and d.endswith("Z")
    cleaned = d.replace("M", "").replace("L", "").replace("Z", "")
    coords = [float(n) for tok in cleaned.split() for n in tok.split(",")]
    xs, ys = coords[0::2], coords[1::2]
    assert all(0 <= x <= VIEWBOX_W for x in xs)
    assert all(0 <= y <= VIEWBOX_H for y in ys)


def test_region_svg_paths_handles_multipolygon():
    from shapely.geometry import MultiPolygon

    p1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    p2 = Polygon([(2, 2), (3, 2), (3, 3), (2, 3)])
    gdf = gpd.GeoDataFrame({"name": ["Islands"]}, geometry=[MultiPolygon([p1, p2])])

    paths = region_svg_paths(gdf, name_column="name", simplify_tolerance=0.001)

    assert paths["Islands"].count("M ") == 2
