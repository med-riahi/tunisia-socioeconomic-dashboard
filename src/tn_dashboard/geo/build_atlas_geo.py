"""Regenerates app/assets/atlas/geo/region_geo3.json: the Mediterranean-basin
establishing shot (Iberia/Alps to Turkey, Atlas mountains to the Sahara) that
the Data Atlas (app/atlas.py) scroll-zooms into Tunisia, plus Tunisia's own
governorate polygons at the tight resting crop.

Previously hand-generated with no build script (a real gap — see git history
for app/atlas.py). This reconstructs it from two source shapefiles:
- data/raw/TUN_adm1.shp: Tunisia governorate/delegation boundaries (dissolved
  to governorate level via tn_dashboard.geo.names).
- data/raw/ne_10m_mediterranean/mediterranean_land.geojson: Natural Earth
  1:10m admin-0 countries (public domain), downloaded from Natural Earth's
  own GitHub mirror and pre-clipped to a generous Mediterranean-basin box
  (see that directory for the one-off clip) so the repo doesn't carry the
  full ~13MB world file for a region that only needs ~2MB of it. 10m is the
  most detailed tier Natural Earth publishes — the previous 110m tier read
  visibly blocky on Mediterranean islands (Sicily, Crete, the Aegean).

Run: python -m tn_dashboard.geo.build_atlas_geo
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import geopandas as gpd

from tn_dashboard.geo.names import add_governorate_column

REPO_ROOT = Path(__file__).resolve().parents[3]
TUN_SHP = REPO_ROOT / "data" / "raw" / "TUN_adm1.shp"
NE_SHP = REPO_ROOT / "data" / "raw" / "ne_10m_mediterranean" / "mediterranean_land.geojson"
OUT_PATH = REPO_ROOT / "app" / "assets" / "atlas" / "geo" / "region_geo3.json"

# Target a typical wide-screen aspect (16:9) for BOTH the establishing shot
# and the resting Tunisia crop below. preserveAspectRatio="slice" (cover —
# fills the screen edge to edge, the actual ask, vs. "meet" which letterboxes
# whenever the viewBox aspect doesn't match the window) only avoids cropping
# real content when the viewBox itself is already close to the container's
# aspect. Matching both endpoints to it means the map fills the screen at
# rest AND at the Tunisia crop, on any typical desktop window.
TARGET_ASPECT = 16 / 9

# Plain degree-for-degree plotting (equirectangular with no standard
# parallel) makes everything at this latitude render ~20% wider than it
# really is — 1 degree of longitude covers noticeably less ground than 1
# degree of latitude the further you get from the equator. Scaling x by
# cos(reference latitude) is the standard correction; using Tunisia's own
# latitude as the reference means Tunisia (what actually gets zoomed into
# and needs to look right, not just the wide shot) renders at true
# proportions. This is what was making the country look "fat" both at rest
# and mid-zoom.
REF_LAT = 34.0
COS_REF_LAT = math.cos(math.radians(REF_LAT))
PX_PER_DEG = 31.5

# Mediterranean establishing-shot bounds: Iberia/Atlas mountains in the west,
# Turkey/the Levant in the east, the Alps' southern slopes in the north,
# deep Sahara in the south — matches the framing of the reference satellite
# photo without needing an actual raster image (see project memory on
# preferring vector for anything that pans/zooms continuously). Longitude
# range is picked to hit TARGET_ASPECT exactly at this latitude band once
# cos-latitude corrected — a plain lon/lat degree box won't generally land
# on 16:9 on its own.
LAT_MIN, LAT_MAX = 19.0, 46.0
LON_MIN = -12.0
LON_MAX = LON_MIN + (LAT_MAX - LAT_MIN) * TARGET_ASPECT / COS_REF_LAT

VIEWBOX_W = round((LON_MAX - LON_MIN) * COS_REF_LAT * PX_PER_DEG, 2)
VIEWBOX_H = round((LAT_MAX - LAT_MIN) * PX_PER_DEG, 2)

# Countries worth naming on the establishing shot, keyed by Natural Earth's
# `name` column. Each is labeled at its own true representative point (not
# clipped to the bbox first) and only kept if that point lands inside the
# viewBox — skip Turkey/Algeria/Libya-style countries whose "true center"
# falls outside this crop rather than mislabeling a clipped sliver.
LABELED_COUNTRIES = [
    "Spain", "France", "Italy", "Greece", "Turkey", "Malta", "Cyprus",
    "Algeria", "Libya", "Egypt", "Morocco",
]


def _project(lon: float, lat: float) -> tuple[float, float]:
    x = (lon - LON_MIN) * COS_REF_LAT * PX_PER_DEG
    y = (LAT_MAX - lat) * PX_PER_DEG
    return round(x, 2), round(y, 2)


def _ring_to_path(coords) -> str:
    pts = [_project(lon, lat) for lon, lat in coords]
    d = f"M {pts[0][0]},{pts[0][1]} " + " ".join(f"L {x},{y}" for x, y in pts[1:])
    return d + " Z"


def _geom_to_path(geom) -> str:
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    parts = []
    for poly in polys:
        parts.append(_ring_to_path(list(poly.exterior.coords)))
        for interior in poly.interiors:
            parts.append(_ring_to_path(list(interior.coords)))
    return " ".join(parts)


def build() -> dict:
    tun = gpd.read_file(TUN_SHP)
    tun = add_governorate_column(tun)
    gov = tun.dissolve(by="Governorate").reset_index()
    gov["geometry"] = gov["geometry"].simplify(0.004, preserve_topology=True)
    gov_paths = {row["Governorate"]: _geom_to_path(row["geometry"]) for _, row in gov.iterrows()}

    country_geom = gov.union_all()
    country_path = _geom_to_path(country_geom)
    minx, miny, maxx, maxy = country_geom.bounds
    pad_x, pad_y = (maxx - minx) * 0.06, (maxy - miny) * 0.06
    tv_topleft = _project(minx - pad_x, maxy + pad_y)
    tv_botright = _project(maxx + pad_x, miny - pad_y)
    tight_w = tv_botright[0] - tv_topleft[0]
    tight_h = tv_botright[1] - tv_topleft[1]

    # A tight crop on just Tunisia's own bbox (aspect ~0.46 — tall and
    # narrow) cropped badly under preserveAspectRatio="slice" on any wide
    # screen: slice fills by whichever dimension needs the LEAST scaling,
    # so a narrow-tall viewBox on a wide-short container gets its height
    # blown up and its top/bottom sliced off (the original "only some
    # governorates visible" bug). Padding width to match TARGET_ASPECT
    # (matching FULL_VIEWBOX below) instead of just the 6% breathing-room
    # pad means "slice" and "meet" behave the same on a typical screen —
    # full country visible, extra sea/neighboring land on the sides,
    # rather than a crop that depends on the viewer's window shape.
    tv_cx = tv_topleft[0] + tight_w / 2
    target_w = tight_h * TARGET_ASPECT
    tunisia_viewbox = [
        round(tv_cx - target_w / 2, 2), tv_topleft[1],
        round(target_w, 2), round(tight_h, 2),
    ]

    # Flag emblem placement: 35% in from the west edge, mid-height —
    # proportional to whatever the previous hand-built version used,
    # rather than a plain bbox centroid, so it sits inside Tunisia's
    # silhouette instead of near an edge. Sized off the tight (unpadded)
    # country crop, not the aspect-widened viewbox above. Radius is
    # smaller than the original 0.287 factor: at rest (p=0) this emblem
    # now renders directly against the hero description text with nothing
    # behind it (previously a raster photo covered the vector map
    # entirely at p=0) — a smaller disc collides with less of the
    # paragraph.
    flag_lon = minx + (maxx - minx) * 0.354
    flag_lat = maxy - (maxy - miny) * 0.516
    flag_cx, flag_cy = _project(flag_lon, flag_lat)
    flag_r = round(tight_w / 1.06 * 0.19, 2)

    ne = gpd.read_file(NE_SHP)
    ne = ne[ne["NAME"] != "Tunisia"]
    bbox_wkt = (
        f"POLYGON(({LON_MIN} {LAT_MIN}, {LON_MAX} {LAT_MIN}, "
        f"{LON_MAX} {LAT_MAX}, {LON_MIN} {LAT_MAX}, {LON_MIN} {LAT_MIN}))"
    )
    bbox = gpd.GeoSeries.from_wkt([bbox_wkt], crs="EPSG:4326").iloc[0]
    ne = ne[ne.intersects(bbox)].copy()
    # 10m source, so a coarser tolerance than the old 110m-tuned 0.03 still
    # keeps real coastline detail (island shapes, bays) while controlling
    # point count/render cost — 0.006 (the first version of this) kept
    # nearly all of 10m's raw density, which was a real contributor to the
    # page feeling heavy once every point was also being glow-filtered.
    ne["geometry"] = ne["geometry"].simplify(0.012, preserve_topology=True)
    # Algeria/Libya's border with Tunisia comes from Natural Earth, while
    # Tunisia's own border comes from the separate, independently-traced
    # TUN_adm1 shapefile — two different tracings of the same physical
    # border never land on the same coordinates, which left a visible
    # sliver of sea showing through the gap between Tunisia and its
    # neighbors even at 10m. Tunisia's own shape draws on top of this land
    # layer (later in the SVG, higher z-order), so buffering the neighbors
    # outward by a small amount tucks the mismatched seam underneath
    # Tunisia's own coastline instead of trying to make two unrelated
    # datasets agree exactly. resolution=4 (default 16) keeps the buffer's
    # own added arc points from bloating the path back up.
    #
    # Only Algeria and Libya get buffered — they're the only countries
    # with an actual land border with Tunisia, so they're the only ones
    # with a seam to fix. Applying the same buffer to every country in the
    # view was a real bug: it silently swallowed narrow water gaps
    # elsewhere that have nothing to do with Tunisia — the Strait of
    # Gibraltar (Spain/Morocco) and the Strait of Messina (Sicily/mainland
    # Italy) are both narrower than 0.12° and were rendering as fused
    # landmasses instead of separated by sea.
    tunisia_land_neighbors = {"Algeria", "Libya"}
    is_neighbor = ne["NAME"].isin(tunisia_land_neighbors)
    ne.loc[is_neighbor, "geometry"] = ne.loc[is_neighbor, "geometry"].buffer(0.12, resolution=4)
    # Each neighboring country is still its own separate polygon at this
    # point, so every shared border between two of them (Algeria/Libya,
    # Spain/France, Italy/Slovenia...) was drawing two glowing strokes
    # right next to each other — the "double lines" seen inland. Dissolving
    # them into one landmass before generating the path leaves only the
    # true coastline stroked; this also further cuts point count (shared
    # inner edges disappear entirely) which helps with render cost too.
    other_geom = ne.geometry.union_all().intersection(bbox)
    other_geom = other_geom.simplify(0.01, preserve_topology=True)
    other_land_path = _geom_to_path(other_geom)

    ne_full = gpd.read_file(NE_SHP)
    labels = []
    for name in LABELED_COUNTRIES:
        rows = ne_full[ne_full["NAME"] == name]
        if rows.empty:
            continue
        pt = rows.iloc[0]["geometry"].representative_point()
        if not (LON_MIN < pt.x < LON_MAX and LAT_MIN < pt.y < LAT_MAX):
            continue
        x, y = _project(pt.x, pt.y)
        labels.append({"name": name.upper(), "x": x, "y": y})

    return {
        "viewbox_w": VIEWBOX_W,
        "viewbox_h": VIEWBOX_H,
        "region_bounds": [LON_MIN, LAT_MIN, LON_MAX, LAT_MAX],
        "gov_paths": gov_paths,
        "country_path": country_path,
        "other_land_path": other_land_path,
        "tunisia_viewbox": tunisia_viewbox,
        "flag_cx": flag_cx,
        "flag_cy": flag_cy,
        "flag_r": flag_r,
        "flag_lon": round(flag_lon, 4),
        "flag_lat": round(flag_lat, 4),
        "labels": labels,
    }


def main() -> None:
    data = build()
    OUT_PATH.write_text(json.dumps(data))
    print(f"wrote {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} KB)")
    label_names = [entry["name"] for entry in data["labels"]]
    print(f"governorates: {len(data['gov_paths'])}, labels: {label_names}")
    print(f"tunisia_viewbox: {data['tunisia_viewbox']}")


if __name__ == "__main__":
    main()
