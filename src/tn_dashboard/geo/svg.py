"""Project governorate/delegation polygons to SVG path data, for the app's
custom choropleth component (see app/map_component.py). Used instead of a
Leaflet/folium map: it renders crisp at any size, needs no basemap tiles,
and sidesteps the iframe-sizing bugs folium/streamlit-folium hit for a
narrow, tall country like Tunisia.
"""

from __future__ import annotations

VIEWBOX_W = 520
VIEWBOX_H = 900
PAD = 10


Bounds = tuple[float, float, float, float]


def _project(lon: float, lat: float, bounds: Bounds) -> tuple[float, float]:
    minx, miny, maxx, maxy = bounds
    x = PAD + (lon - minx) / (maxx - minx) * (VIEWBOX_W - 2 * PAD)
    y = PAD + (1 - (lat - miny) / (maxy - miny)) * (VIEWBOX_H - 2 * PAD)
    return x, y


def _ring_to_path(coords, bounds) -> str:
    pts = [_project(lon, lat, bounds) for lon, lat in coords]
    d = f"M {pts[0][0]:.1f},{pts[0][1]:.1f} " + " ".join(f"L {x:.1f},{y:.1f}" for x, y in pts[1:])
    return d + " Z"


def _geom_to_path(geom, bounds) -> str:
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    parts = []
    for poly in polys:
        parts.append(_ring_to_path(list(poly.exterior.coords), bounds))
        for interior in poly.interiors:
            parts.append(_ring_to_path(list(interior.coords), bounds))
    return " ".join(parts)


def region_svg_paths(gdf, name_column: str, simplify_tolerance: float = 0.006) -> dict[str, str]:
    """Return {region_name: svg_path_d} for every row in `gdf`, projected
    into a 0..VIEWBOX_W x 0..VIEWBOX_H space sized to `gdf`'s own bounds.
    """
    simplified = gdf.copy()
    simplified["geometry"] = simplified["geometry"].simplify(
        simplify_tolerance, preserve_topology=True
    )
    bounds = tuple(simplified.total_bounds)
    return {
        row[name_column]: _geom_to_path(row["geometry"], bounds)
        for _, row in simplified.iterrows()
    }
