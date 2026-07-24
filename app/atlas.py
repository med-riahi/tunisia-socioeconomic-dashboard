"""Tunisia Data Atlas — the cinematic scroll-driven governorate explorer.

Generates one self-contained HTML/CSS/JS document (fonts, monument photos,
and the national emblem all embedded as base64 data URIs — no external
requests at render time) from real data in ``data/tunisia.duckdb``. Embedded
into the Streamlit app via ``st.components.v1.html`` in ``streamlit_app.py``.

Design notes carried over from the prototyping session:
- Custom equirectangular-ish SVG projection (see ``tn_dashboard.geo.svg``)
  instead of folium/Leaflet — a scroll-driven viewBox zoom needs direct
  control over the SVG, which an iframe-based tile map doesn't give you.
- The flag emblem's crescent/star geometry is reproduced from the exact
  ratios in Wikimedia's own minimal official Tunisian flag SVG (disc r=20,
  outer crescent circle r=15 at the SAME center as the disc, inner cutout
  circle r=12 offset +4 in x, star center coincident with that cutout
  circle, outer radius 9, pentagram construction stepping 144° per vertex
  starting at 180°) — not an approximation.
- Typeface: El Messiri, a single variable font (wght 400-700) that natively
  pairs Arabic and Latin with correct GSUB letter-joining. Tried Cairo (too
  generic/overused), then Markazi Text (too calligraphic), before settling
  back here — El Messiri has enough editorial character without tipping into
  manuscript territory. Every candidate along the way was verified by
  rendering a real sample before committing (this is exactly the class of
  mistake that broke Arabic shaping once before with a different font).
- None of Tunisia's 24 governorates has an official governorate-level coat
  of arms (checked against French Wikipedia's infobox wikitext for all 24
  "Gouvernorat de X" articles). Each panel instead shows a real, verified
  photo of that governorate's most famous monument/landmark plus a short
  excerpt condensed from its English Wikipedia article — see GOV_MONUMENTS
  and GOV_TEXT below for sourcing/credit on every single one.
"""

from __future__ import annotations

import base64
import json
import math
from pathlib import Path

import pandas as pd

ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "atlas"

# The ETL stores governorate names straight from the INS API's own region
# tree (accented French spellings). The map/panel keys used throughout this
# module are the unaccented canonical forms from tn_dashboard.config, same
# as the shapefile-matching side of the pipeline uses.
DB_GOVERNORATE_TO_CANONICAL = {
    "Ben Arous": "Ben Arous",
    "Bizerte": "Bizerte",
    "Bèja": "Beja",
    "Gabès": "Gabes",
    "Gafsa": "Gafsa",
    "Jendouba": "Jendouba",
    "Kairouan": "Kairouan",
    "Kasserine": "Kasserine",
    "Kef": "Kef",
    "Kébili": "Kebili",
    "L'Ariana": "Ariana",
    "Mahdia": "Mahdia",
    "Manouba": "Manouba",
    "Medenine": "Medenine",
    "Monastir": "Monastir",
    "Nabeul": "Nabeul",
    "Sfax": "Sfax",
    "Sidi Bouzid": "Sidi Bouzid",
    "Siliana": "Siliana",
    "Sousse": "Sousse",
    "Tataouine": "Tataouine",
    "Tozeur": "Tozeur",
    "Tunis": "Tunis",
    "Zaghouan": "Zaghouan",
}

TRILINGUAL = {
    "Tunis": {"ar": "تونس", "fr": "Tunis", "en": "Tunis"},
    "Ariana": {"ar": "أريانة", "fr": "L'Ariana", "en": "Ariana"},
    "Ben Arous": {"ar": "بن عروس", "fr": "Ben Arous", "en": "Ben Arous"},
    "Manouba": {"ar": "منوبة", "fr": "La Manouba", "en": "Manouba"},
    "Nabeul": {"ar": "نابل", "fr": "Nabeul", "en": "Nabeul"},
    "Zaghouan": {"ar": "زغوان", "fr": "Zaghouan", "en": "Zaghouan"},
    "Bizerte": {"ar": "بنزرت", "fr": "Bizerte", "en": "Bizerte"},
    "Beja": {"ar": "باجة", "fr": "Béja", "en": "Beja"},
    "Jendouba": {"ar": "جندوبة", "fr": "Jendouba", "en": "Jendouba"},
    "Kef": {"ar": "الكاف", "fr": "Le Kef", "en": "Kef"},
    "Siliana": {"ar": "سليانة", "fr": "Siliana", "en": "Siliana"},
    "Sousse": {"ar": "سوسة", "fr": "Sousse", "en": "Sousse"},
    "Monastir": {"ar": "المنستير", "fr": "Monastir", "en": "Monastir"},
    "Mahdia": {"ar": "المهدية", "fr": "Mahdia", "en": "Mahdia"},
    "Sfax": {"ar": "صفاقس", "fr": "Sfax", "en": "Sfax"},
    "Kairouan": {"ar": "القيروان", "fr": "Kairouan", "en": "Kairouan"},
    "Kasserine": {"ar": "القصرين", "fr": "Kasserine", "en": "Kasserine"},
    "Sidi Bouzid": {"ar": "سيدي بوزيد", "fr": "Sidi Bouzid", "en": "Sidi Bouzid"},
    "Gabes": {"ar": "قابس", "fr": "Gabès", "en": "Gabes"},
    "Medenine": {"ar": "مدنين", "fr": "Médenine", "en": "Medenine"},
    "Tataouine": {"ar": "تطاوين", "fr": "Tataouine", "en": "Tataouine"},
    "Gafsa": {"ar": "قفصة", "fr": "Gafsa", "en": "Gafsa"},
    "Tozeur": {"ar": "توزر", "fr": "Tozeur", "en": "Tozeur"},
    "Kebili": {"ar": "قبلي", "fr": "Kébili", "en": "Kebili"},
}

# Only 13 of the 48 approved indicators actually carry governorate-level
# rows (the rest are national-only). The map's color still comes from one
# headline slug per theme, but the national stat-card rail below the legend
# now surfaces the OTHER real governorate-level indicators in that same DB
# theme_group too, aggregated to a country total/average — rather than
# leaving them unused just because the choropleth can only show one
# indicator's colors at a time. "sum" aggregates are for counts (population,
# schools, branches); "mean" aggregates are for rates/ratios.
THEMES = {
    "population": {
        "label": "Population", "slug": "birth_rate", "unit": "/ 1,000 hab.",
        "stats": [
            {"slug": "population_jan1", "label": "Total population", "agg": "sum", "unit": ""},
            {"slug": "birth_rate", "label": "Avg. birth rate", "agg": "mean", "unit": "/1,000"},
            {"slug": "death_rate", "label": "Avg. death rate", "agg": "mean", "unit": "/1,000"},
            {"slug": "deaths_total_corrected", "label": "Deaths (total)", "agg": "sum", "unit": ""},
            {"slug": "divorces", "label": "Divorces (total)", "agg": "sum", "unit": ""},
        ],
    },
    "economy": {
        "label": "Economy", "slug": "bank_branches_by_governorate", "unit": "branches",
        "stats": [
            {"slug": "bank_branches_by_governorate", "label": "Bank branches (total)", "agg": "sum", "unit": ""},
            {"slug": "bank_branches_by_governorate", "label": "Avg. per governorate", "agg": "mean", "unit": ""},
            {"slug": "bank_branches_by_governorate", "label": "Leading governorate", "agg": "max_gov", "unit": ""},
        ],
    },
    "health": {
        "label": "Health & Education", "slug": "hospital_beds_per_1000", "unit": "/ 1,000 people",
        "stats": [
            {"slug": "hospital_beds_count", "label": "Hospital beds (total)", "agg": "sum", "unit": ""},
            {"slug": "general_hospitals_count", "label": "General hospitals", "agg": "sum", "unit": ""},
            {"slug": "regional_hospitals_count", "label": "Regional hospitals", "agg": "sum", "unit": ""},
            {"slug": "public_doctors_count", "label": "Public-sector doctors", "agg": "sum", "unit": ""},
            {"slug": "nurses_count", "label": "Nurses", "agg": "sum", "unit": ""},
            {"slug": "dental_clinics_count", "label": "Dental clinics", "agg": "sum", "unit": ""},
            {"slug": "primary_schools_count", "label": "Primary schools", "agg": "sum", "unit": ""},
            {"slug": "secondary_establishments_count", "label": "Secondary schools", "agg": "sum", "unit": ""},
            {"slug": "prenatal_care_acts", "label": "Prenatal care visits", "agg": "sum", "unit": ""},
        ],
    },
}

GOV_MONUMENTS = {
    "Tunis": {"file": "tunis.jpg", "name": "Sidi Bou Said",
              "credit": "Habib M'henni, CC BY 4.0, Wikimedia Commons"},
    "Ariana": {"file": "ariana.jpg", "name": "Sebkha Ariana",
               "credit": "Citizen59, CC BY-SA 3.0, Wikimedia Commons"},
    "Ben Arous": {"file": "ben_arous.jpg", "name": "Uthina (Oudhna) Roman amphitheatre",
                  "credit": "M.Rais, CC BY-SA 3.0, Wikimedia Commons"},
    "Manouba": {"file": "manouba.jpg", "name": "Kobbet Ennhas Palace",
                "credit": "Rais67, public domain, Wikimedia Commons"},
    "Nabeul": {"file": "nabeul.jpg", "name": "Hammamet beach",
               "credit": "Mohatatou, CC BY-SA 4.0, Wikimedia Commons"},
    "Zaghouan": {"file": "zaghouan.jpg", "name": "Temple of the Waters, Zaghouan",
                 "credit": "Citizen59, CC BY 3.0 + GFDL, Wikimedia Commons"},
    "Bizerte": {"file": "bizerte.jpg", "name": "Old Port of Bizerte",
                "credit": "Kalechnizar, CC BY-SA 3.0, Wikimedia Commons"},
    "Beja": {"file": "beja.jpg", "name": "Dougga (Thugga), UNESCO WHS 1997",
             "credit": "Slim Alileche, CC BY-SA 3.0, Wikimedia Commons"},
    "Jendouba": {"file": "jendouba.jpg", "name": "Bulla Regia",
                 "credit": "Pradigue, CC BY-SA 3.0 + GFDL, Wikimedia Commons"},
    "Kef": {"file": "kef.jpg", "name": "Kasbah of Le Kef",
            "credit": "Ena Tounes, CC BY 2.0, Wikimedia Commons"},
    "Siliana": {"file": "siliana.jpg", "name": "Maktar (Mactaris), Arch of Trajan",
                "credit": "Pradigue, CC BY 3.0, Wikimedia Commons"},
    "Sousse": {"file": "sousse.jpg", "name": "Sousse coastline at sunset",
               "credit": "Eyakaddour, CC BY-SA 4.0, Wikimedia Commons"},
    "Monastir": {"file": "monastir.jpg", "name": "Monastir beach and corniche",
                 "credit": "David Stanley, CC BY 2.0, Wikimedia Commons"},
    "Mahdia": {"file": "mahdia.jpg", "name": "Cap Africa Lighthouse, Mahdia",
               "credit": "Habib M'henni, CC BY 4.0, Wikimedia Commons"},
    "Sfax": {"file": "sfax.jpg", "name": "Great Mosque of Sfax",
             "credit": "IssamBarhoumi, CC BY-SA 4.0, Wikimedia Commons"},
    "Kairouan": {"file": "kairouan.jpg", "name": "Great Mosque of Kairouan",
                 "credit": "WT-shared Shoestring, CC BY-SA, Wikimedia Commons"},
    "Kasserine": {"file": "kasserine.jpg", "name": "Arch of Diocletian, Sbeitla",
                  "credit": "Dennis G. Jarvis, CC BY-SA 2.0, Wikimedia Commons"},
    "Sidi Bouzid": {"file": "sidi_bouzid.jpg", "name": "Zaouia of Sidi Ali Ben Aoun",
                    "credit": "Houss 2020, CC0 public domain, Wikimedia Commons"},
    "Gabes": {"file": "gabes.jpg", "name": "Gabès Oasis",
              "credit": "Elcèd77, CC BY-SA 3.0 + GFDL, Wikimedia Commons"},
    "Medenine": {"file": "medenine.jpg", "name": "Fishing boats, Sidi Jmour, Djerba",
                 "credit": "Langar mehdi, CC BY-SA 4.0, Wikimedia Commons"},
    "Tataouine": {"file": "tataouine.jpg", "name": "Ksar Ouled Soltane",
                  "credit": "Ian Sewell, CC BY 2.5, Wikimedia Commons"},
    "Gafsa": {"file": "gafsa.jpg", "name": "Roman Baths of Gafsa",
              "credit": "Habib M'henni, CC BY-SA 3.0, Wikimedia Commons"},
    "Tozeur": {"file": "tozeur.jpg", "name": "Chott el Djerid",
               "credit": "Vinzenz Mühlstein, public domain, Wikimedia Commons"},
    "Kebili": {"file": "kebili.jpg", "name": "Douz, gateway to the Sahara",
               "credit": "Smailtn (Ismail Saidi), CC BY-SA 4.0, Wikimedia Commons"},
}

GOV_TEXT = {
    "Tunis": "Tunisia's capital region — smallest by area (346 km²) but most populous, at 1,075,306 people (2024). Established 21 June 1956; the Medina of Tunis has been a UNESCO World Heritage Site since 1979.",
    "Ariana": "A northern suburb of Greater Tunis, 482 km² with 668,552 people (2024) — the 6th most populous governorate. Established in March 1983.",
    "Ben Arous": "Part of Greater Tunis, 761 km² with 722,828 people (2024). Established 3 December 1983; home to Radès, Tunisia's main commercial port.",
    "Manouba": "The 4th Greater Tunis governorate, created 31 July 2000 from Ariana's delegations. 1,137 km², population 379,518 (2014).",
    "Nabeul": "2,788 km² on the Cap Bon peninsula, population 863,172 (2024). Nabeul city was founded in the 5th century BC by Greek settlers from Cyrene.",
    "Zaghouan": "2,768 km², population 176,945 (2014), established November 1976. Traditionally agricultural — about a third of the workforce farms.",
    "Bizerte": "Tunisia's northernmost governorate, 3,750 km² with 607,388 people (2024). Home to Lake Ichkeul (UNESCO WHS) and the ruins of ancient Utica.",
    "Beja": "3,740 km² in the Tell Atlas hills, population 303,032 (2014). Established June 1956; Dougga, North Africa's best-preserved small Roman town, sits within its borders.",
    "Jendouba": "3,102 km², population 401,477 (2014). Formerly Souk El Arba Governorate, renamed in 1966 — mountainous and agricultural, with the Roman/Numidian site of Bulla Regia.",
    "Kef": "4,965 km², one of the larger governorates by area, population 243,156 (2014). El Kef served as an FLN command centre during the Algerian War of Independence.",
    "Siliana": "4,631 km², population 223,087 (2014), established 5 June 1974 — a crossing point between northern and central Tunisia.",
    "Sousse": "2,669 km², population 762,281 (2024), the 4th most populous governorate and a major tourism hub. The Medina of Sousse has been UNESCO-listed since 1988.",
    "Monastir": "1,019 km², population 599,769 (2024), established 5 June 1974. Economy built on olive agriculture and textiles; its Ribat is among the oldest and best-preserved in North Africa.",
    "Mahdia": "2,966 km², population 410,812 (2014), created 9 March 1974 by splitting from Sousse. Includes El Djem, seat of one of the best-preserved Roman amphitheatres in the world.",
    "Sfax": "7,545 km² including the Kerkennah Islands, population 1,047,468 — Tunisia's 2nd most populous governorate. Its walled medina, built by the Aghlabids in the 9th century, centers on the Great Mosque.",
    "Kairouan": "6,712 km², population 600,803 (2024), established 21 June 1956. The Great Mosque of Uqba is among the oldest and most important mosques in Islam.",
    "Kasserine": "8,260 km² on the Algerian border, population 492,741 (2024), at the foot of Jebel ech Chambi — Tunisia's highest peak. Sbeitla's Roman ruins include well-preserved Capitoline temples.",
    "Sidi Bouzid": "A landlocked, largely agricultural governorate of 7,405 km², population 429,912 (2014). Known worldwide as the birthplace of the 2010–11 Tunisian Revolution, sparked by Mohamed Bouazizi's protest on 17 December 2010.",
    "Gabes": "7,166 km², population 374,300 (2014), established June 1956. Known for a rare coastal oasis (on UNESCO's Tentative List since 2008) and a major fishing/chemical industry.",
    "Medenine": "9,167 km² — the 3rd largest by area — bordering Libya, population 537,255 (2024). Administratively includes Djerba, home to over a third of the governorate's population.",
    "Tataouine": "Tunisia's southernmost and largest governorate at 38,889 km², population 149,453 (2014). The only governorate bordering both Algeria and Libya; its ksour inspired the name \"Tatooine\" in Star Wars.",
    "Gafsa": "7,807 km², population 337,331 (2014). Economy centred on phosphate extraction and irrigated oasis fruit-growing; ancient Capsa retains well-preserved open-air Roman baths.",
    "Tozeur": "Tunisia's westernmost governorate, 4,719 km², population 107,912 (2014) — the least populated. Reintegrated into Gafsa in 1958, restored as its own governorate in 1980; salt lakes cover roughly 45% of its terrain.",
    "Kebili": "22,454 km², Tunisia's 2nd-largest governorate by area, population 156,961 (2014), established September 1981. Known for deglet nour dates and Sahara-edge tourism centred on Douz.",
}


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def _static_assets() -> dict:
    """Fonts, geometry, national emblem, monument photos — reloaded from
    disk every call. This was previously cached with @lru_cache for the
    process lifetime, which meant edits to the geo/font/photo files never
    showed up in an already-running `streamlit run` session (only a hard
    restart picked them up) — a real source of "I already fixed that"
    confusion during active iteration. These files are small; reloading
    them each render is cheap enough not to matter."""
    geo = json.loads((ASSETS_DIR / "geo" / "region_geo3.json").read_text())
    africa = json.loads((ASSETS_DIR / "geo" / "africa_inset.json").read_text())
    monuments = {}
    for gov, m in GOV_MONUMENTS.items():
        monuments[gov] = {**m, "b64": _b64(ASSETS_DIR / "monuments" / m["file"])}
    return {
        "cairo_latin_b64": _b64(ASSETS_DIR / "fonts" / "elmessiri_latin.woff2"),
        "cairo_arabic_b64": _b64(ASSETS_DIR / "fonts" / "elmessiri_arabic.woff2"),
        "reemkufi_b64": _b64(ASSETS_DIR / "fonts" / "reemkufi_hud.woff2"),
        "orbitron_b64": _b64(ASSETS_DIR / "fonts" / "orbitron_hud.woff2"),
        "coat_b64": (ASSETS_DIR / "coat_of_arms.b64").read_text().strip(),
        "geo": geo,
        "africa": africa,
        "monuments": monuments,
    }


def _official_star_points(cx, cy, r, start_angle_deg=180):
    """Reproduces the exact pentagram construction used in the authoritative
    flag artwork (Wikimedia's minimal official SVG): 5 vertices on one
    circle, connected every 144° (i.e. every 2nd vertex of a regular
    pentagon), one vertex aimed due left (180°)."""
    pts = []
    for i in range(5):
        angle = math.radians(start_angle_deg + i * 144)
        pts.append((round(cx + r * math.cos(angle), 3), round(cy + r * math.sin(angle), 3)))
    return pts


def _radar_sweep_svg(cx: float, cy: float, r: float, arc_deg: float = 55, n: int = 18) -> str:
    """A rotating "sweep beam" out of thin radial lines with decreasing
    opacity from leading to trailing edge — SVG has no conic-gradient to
    fade a wedge azimuthally, so this fakes the classic radar-sweep trail
    with N lines instead of one filled shape. Grouped and spun via CSS
    (see .radar-sweep / @keyframes radarSpin); transform-origin is set
    inline here since it has to match this exact cx/cy, not a shared value
    every instance of the class could use."""
    lines = []
    for i in range(n):
        t = i / (n - 1)
        angle = math.radians(-t * arc_deg)
        x2 = cx + r * math.cos(angle)
        y2 = cy + r * math.sin(angle)
        opacity = round(0.55 * (1 - t) ** 1.6, 3)
        lines.append(
            f'<line x1="{cx}" y1="{cy}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="var(--hud)" stroke-width="0.5" opacity="{opacity}"/>'
        )
    return (
        f'<g class="radar-sweep" style="transform-origin: {cx}px {cy}px">'
        + "".join(lines) + "</g>"
    )


def _slug_values(df: pd.DataFrame, slug: str, label: str) -> dict:
    """Governorate-level values for one slug, keyed by canonical governorate
    name, at that slug's own latest available year."""
    sub = df[(df["slug"] == slug) & (df["region_level"] == "governorate")]
    if sub.empty:
        return {"label": label, "year": None, "values": {}}
    latest_year = int(sub["year"].max())
    sub = sub[sub["year"] == latest_year].dropna(subset=["value"])
    values = {
        DB_GOVERNORATE_TO_CANONICAL.get(row["governorate"], row["governorate"]): float(row["value"])
        for _, row in sub.iterrows()
    }
    return {"label": label, "year": latest_year, "values": values}


def _theme_data(df: pd.DataFrame) -> dict:
    """Every slug referenced anywhere in THEMES (both the one driving the
    map's color and the ones only feeding the national stat cards), keyed by
    slug so the frontend can look any of them up by name."""
    out = {}
    for theme in THEMES.values():
        for slug in {theme["slug"]} | {s["slug"] for s in theme.get("stats", [])}:
            if slug not in out:
                out[slug] = _slug_values(df, slug, theme["label"])
    return out


def _national_stats(data: dict) -> dict:
    """Country-level aggregate per theme, computed from the governorate
    values already pulled in `data` — sum for counts, mean for rates, and a
    "max_gov" variant that names the leading governorate instead of just a
    number, so the economy theme (which only has one real indicator) still
    shows something more than a single repeated figure."""
    out = {}
    for theme_key, theme in THEMES.items():
        cards = []
        for stat in theme.get("stats", []):
            values = data.get(stat["slug"], {}).get("values", {})
            if not values:
                cards.append({"label": stat["label"], "value": None, "unit": stat["unit"]})
                continue
            if stat["agg"] == "sum":
                v = sum(values.values())
                cards.append({"label": stat["label"], "value": round(v), "unit": stat["unit"]})
            elif stat["agg"] == "mean":
                v = sum(values.values()) / len(values)
                cards.append({"label": stat["label"], "value": round(v, 1), "unit": stat["unit"]})
            elif stat["agg"] == "max_gov":
                gov = max(values, key=values.get)
                cards.append({"label": stat["label"], "value": gov, "sub": values[gov], "unit": stat["unit"]})
        out[theme_key] = cards
    return out


def build_atlas_html(df: pd.DataFrame) -> str:
    """Returns the full self-contained Atlas HTML document, ready to hand to
    st.components.v1.html. ``df`` is the same tidy indicators frame the rest
    of the app reads (db.load_indicators())."""
    assets = _static_assets()
    cairo_latin_b64 = assets["cairo_latin_b64"]
    cairo_arabic_b64 = assets["cairo_arabic_b64"]
    orbitron_b64 = assets["orbitron_b64"]
    reemkufi_b64 = assets["reemkufi_b64"]
    coat_b64 = assets["coat_b64"]
    geo = assets["geo"]
    africa = assets["africa"]
    monuments = assets["monuments"]

    data = _theme_data(df)
    national_stats = _national_stats(data)

    W, H = geo["viewbox_w"], geo["viewbox_h"]
    GOV_PATHS = geo["gov_paths"]
    COUNTRY_PATH = geo["country_path"]
    OTHER_LAND_PATH = geo["other_land_path"]
    TUNISIA_VIEWBOX = geo["tunisia_viewbox"]
    LAND_LABELS = geo.get("labels", [])
    FULL_VIEWBOX = [0, 0, W, H]

    flag_cx = geo["flag_cx"]
    flag_cy = geo["flag_cy"]
    flag_r = geo["flag_r"]
    crescent_outer_r = flag_r * (15 / 20)
    crescent_inner_r = flag_r * (12 / 20)
    crescent_offset = flag_r * (4 / 20)
    star_r = flag_r * (9 / 20)
    star_cx = flag_cx + crescent_offset
    star_cy = flag_cy
    STAR_PTS = " ".join(f"{x},{y}" for x, y in _official_star_points(star_cx, star_cy, star_r))

    lat_ns = "N" if geo["flag_lat"] >= 0 else "S"
    lon_ew = "E" if geo["flag_lon"] >= 0 else "W"
    COORD_READOUT = f'{abs(geo["flag_lat"]):.4f}°{lat_ns}  {abs(geo["flag_lon"]):.4f}°{lon_ew}'
    # Rings/sweep are sized off the full establishing-shot viewBox, not
    # Tunisia's own size, so they genuinely sweep across the whole map
    # rather than staying a small halo around the country.
    RING_BASE_R = min(W, H) * 0.045
    RADAR_SWEEP_SVG = _radar_sweep_svg(flag_cx, flag_cy, max(W, H) * 0.62)
    CROSSHAIR_R = flag_r * 2.6
    CROSSHAIR_TICK = flag_r * 3.1

    MONUMENTS_JS = {
        gov: {"b64": m["b64"], "name": m["name"], "credit": m["credit"]}
        for gov, m in monuments.items()
    }
    PAYLOAD = {"trilingual": TRILINGUAL, "themes": THEMES, "data": data,
               "monuments": MONUMENTS_JS, "text": GOV_TEXT, "nationalStats": national_stats}

    html = f'''<title>Tunisia — Data Atlas</title>
<style>
@font-face {{ font-family: "El Messiri"; src: url(data:font/woff2;base64,{cairo_latin_b64}) format("woff2-variations"), url(data:font/woff2;base64,{cairo_latin_b64}) format("woff2"); font-weight: 400 700; font-display: swap; unicode-range: U+0000-024F,U+2000-206F,U+2122; }}
@font-face {{ font-family: "El Messiri"; src: url(data:font/woff2;base64,{cairo_arabic_b64}) format("woff2-variations"), url(data:font/woff2;base64,{cairo_arabic_b64}) format("woff2"); font-weight: 400 700; font-display: swap; unicode-range: U+0600-06FF,U+200C-200F,U+FEFF; }}
@font-face {{ font-family: "Orbitron HUD"; src: url(data:font/woff2;base64,{orbitron_b64}) format("woff2-variations"), url(data:font/woff2;base64,{orbitron_b64}) format("woff2"); font-weight: 400 900; font-display: swap; }}
/* Reem Kufi: a modern text revival of Kufic script — Kufic's native
   geometry (angular, squared-off strokes) already reads as "technical"
   the way Latin geometric sans faces do, without inventing a fake
   futuristic treatment on top of Arabic letterforms. Pairs with Orbitron
   for the Latin/digital side of the same HUD language. */
@font-face {{ font-family: "Reem Kufi HUD"; src: url(data:font/woff2;base64,{reemkufi_b64}) format("woff2-variations"), url(data:font/woff2;base64,{reemkufi_b64}) format("woff2"); font-weight: 400 700; font-display: swap; unicode-range: U+0600-06FF,U+200C-200F,U+FEFF; }}

:root {{
  --bg: #05070b;
  --bg-2: #0b0f16;
  --bg-3: #131922;
  --sea: #0a2740;
  --land: #3a3226;
  --ink: #eef1f6;
  --ink-2: #8b93a3;
  --ink-3: #545c6c;
  --red: #e70013;
  --red-glow: rgba(231,0,19,0.5);
  --gold: #d4a94a;
  --grid: rgba(238,241,246,0.05);
  --border: rgba(238,241,246,0.10);
  --hud: #4be8ff;
  --hud-dim: rgba(75,232,255,0.35);
}}

* {{ box-sizing: border-box; }}
/* no overflow-x:hidden here — setting only overflow-x on body forces
   overflow-y to compute as auto per the CSS overflow spec, which breaks
   position:sticky for every sticky element on the page. Nothing here
   actually overflows horizontally (everything is width:100%/inset:0), so
   there's nothing to clip in the first place. */
html, body {{ margin: 0; padding: 0; background: var(--bg); }}
body {{ font-family: "El Messiri", -apple-system, BlinkMacSystemFont, sans-serif; color: var(--ink); }}
[lang="ar"], .ar {{ direction: rtl; font-family: "Reem Kufi HUD", "El Messiri", sans-serif; }}

/* 220vh made the zoom-to-Tunisia complete by ~58% of the total scrollable
   distance (measured directly: viewBox stopped changing well before the
   page's actual scroll end), leaving the back half of the scroll doing
   nothing and making the whole transition feel like it snapped shut after
   a couple of scroll gestures instead of unfolding gradually. More runway
   fixes that without changing anything about what each scroll fraction
   shows. */
.scroll-spacer {{ height: 340vh; }}

.hero {{
  position: sticky; top: 0; height: 100vh;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background:
    radial-gradient(ellipse at 50% 40%, rgba(231,0,19,0.08), transparent 55%),
    repeating-linear-gradient(0deg, var(--grid) 0 1px, transparent 1px 48px),
    repeating-linear-gradient(90deg, var(--grid) 0 1px, transparent 1px 48px),
    var(--bg);
  z-index: 1; overflow: hidden;
}}
.terminal-hint .chevron {{
  display: block; margin: 8px auto 0; width: 9px; height: 9px;
  border-right: 1.5px solid var(--hud); border-bottom: 1.5px solid var(--hud);
  transform: rotate(45deg); animation: bob 1.8s ease-in-out infinite;
}}
@keyframes bob {{ 0%,100% {{ transform: rotate(45deg) translate(0,0); }} 50% {{ transform: rotate(45deg) translate(4px,4px); }} }}

/* Terminal boot sequence: a dark, mapless first screen that types out a
   short boot log before the Mediterranean establishing shot even appears
   — the map is the payoff of a "system locating its target" beat, not
   the first thing you see. Not sticky (unlike .hero): it's meant to
   scroll away entirely once read, handing off to the map section that
   follows. onScroll (below) offsets its own scroll math by this
   element's height so the zoom doesn't start until this has scrolled
   out of view. */
.terminal-intro {{
  height: 100vh; width: 100%; background: var(--bg);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  position: relative; z-index: 1;
  background-image:
    repeating-linear-gradient(0deg, var(--grid) 0 1px, transparent 1px 48px),
    repeating-linear-gradient(90deg, var(--grid) 0 1px, transparent 1px 48px);
}}

/* Title/coat-of-arms/subline live here now, not on the map — scrolling
   past this screen hands off to a completely clean map with no text
   overlaid on it. Recolored out of the flag red entirely (cyan, matching
   every other HUD element) since this is the terminal, not the flag. */
.terminal-title {{ display: flex; flex-direction: column; align-items: center; margin-bottom: 40px; }}
.terminal-title .coat {{
  width: 30px; height: auto; margin-bottom: 14px;
  filter: drop-shadow(0 0 3px var(--hud)) drop-shadow(0 0 8px var(--hud-dim));
}}
.terminal-title-en {{
  font-family: "Orbitron HUD", monospace; font-weight: 800;
  font-size: clamp(40px, 6.5vw, 92px); letter-spacing: 0.04em; line-height: 0.95;
  color: var(--hud); text-shadow: 0 0 10px var(--hud-dim), 0 0 28px rgba(75,232,255,0.35);
}}
.terminal-title-tag {{
  font-family: "Orbitron HUD", monospace; font-size: 12.5px; letter-spacing: 0.14em;
  text-transform: uppercase; color: var(--hud); opacity: 0.7; margin-top: 8px;
}}
.terminal-subline {{ display: flex; align-items: baseline; gap: 22px; margin-top: 16px; }}
.terminal-subline .fr {{
  font-family: "Orbitron HUD", monospace; font-size: 12.5px; font-weight: 600; letter-spacing: 0.16em;
  text-transform: uppercase; color: var(--hud); opacity: 0.75;
}}
.terminal-subline .ar {{ font-size: 17px; color: var(--hud); opacity: 0.75; }}

/* Ammar: a digitalized "talking mascot" next to the boot text, chomping
   continuously like Pac-Man while the typewriter runs — a chechia (the
   traditional Tunisian felt cap) is what makes it "Ammar" rather than a
   generic arcade sprite. */
.terminal-guide {{ display: flex; align-items: center; gap: 28px; }}
.pacman {{ width: 68px; height: 75px; flex-shrink: 0; filter: drop-shadow(0 0 5px var(--hud-dim)); }}
.pacman-head {{ fill: #ffd94a; }}
.pacman-eye {{ fill: #241a08; }}
.jaw {{ fill: var(--bg); transform-origin: 50px 60px; }}
.jaw-top {{ animation: jawTop 0.6s ease-in-out infinite; }}
.jaw-bottom {{ animation: jawBottom 0.6s ease-in-out infinite; }}
@keyframes jawTop {{ 0%, 100% {{ transform: rotate(0deg); }} 50% {{ transform: rotate(-30deg); }} }}
@keyframes jawBottom {{ 0%, 100% {{ transform: rotate(0deg); }} 50% {{ transform: rotate(30deg); }} }}
.chechia {{ fill: var(--red); }}
.chechia-tassel {{ fill: #1a1200; }}

.terminal-lines {{
  font-family: "Orbitron HUD", monospace; font-size: clamp(13px, 2vw, 20px);
  color: var(--hud); letter-spacing: 0.09em; text-align: left; min-height: 4.2em;
}}
.terminal-line {{ line-height: 2; text-shadow: 0 0 8px var(--hud-dim); }}
.terminal-cursor {{
  display: inline-block; width: 0.5em; height: 1em; background: var(--hud);
  margin-left: 3px; vertical-align: text-bottom; box-shadow: 0 0 6px var(--hud);
  animation: cursorBlink 0.9s steps(1) infinite;
}}
@keyframes cursorBlink {{ 0%, 50% {{ opacity: 1; }} 51%, 100% {{ opacity: 0; }} }}
.terminal-hint {{
  position: absolute; bottom: 8vh; font-family: "Orbitron HUD", monospace; font-size: 11px;
  letter-spacing: 0.24em; color: var(--hud); opacity: 0; text-transform: uppercase;
  transition: opacity 600ms ease; text-align: center;
}}
.terminal-hint.show {{ opacity: 0.75; }}

.locator {{
  position: absolute; top: 28px; right: 34px; z-index: 3;
  width: 132px; padding: 12px; background: rgba(11,15,22,0.6); backdrop-filter: blur(6px);
  border: 1px solid var(--border); border-radius: 10px;
  opacity: 0; transition: opacity 300ms ease;
}}
.locator.show {{ opacity: 1; }}
.locator-label {{
  font-family: Menlo, monospace; font-size: 8.5px; letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--ink-3); text-align: center; margin-top: 6px;
}}

.map-canvas-wrap {{ position: absolute; inset: 0; z-index: 2; display: flex; align-items: center; justify-content: center; }}
svg.atlas-map {{ width: 100%; height: 100%; }}
.hud-grid {{ opacity: 0.55; }}
/* Split into two paths sharing the same `d`: drop-shadow shadows an
   element's whole rendered alpha, fill included — on one path with both a
   large fill (most of Algeria/Libya/Europe) and a glow stroke, that
   blurred the ENTIRE landmass into a cyan wash instead of just glowing
   the coastline. A fill-only path (no glow) plus a stroke-only path
   (glow, no fill) keeps the glow on just the outline. */
.land-fill {{ fill: rgba(9,22,26,0.55); }}
.land-glow {{
  fill: none; stroke: var(--hud); stroke-width: 0.55; opacity: 0.85;
  /* CSS drop-shadow instead of a custom feGaussianBlur+feMerge filter —
     the old version re-rasterized a full multi-pass blur over the entire
     (large, detailed) coastline on every scroll-driven viewBox change,
     which was the main source of the page feeling heavy. drop-shadow is
     cheaper and its blur radius is tied directly to the shadow, not a
     fixed 220% oversized filter region. */
  filter: drop-shadow(0 0 1.4px var(--hud)) drop-shadow(0 0 3.5px var(--hud-dim));
}}
.sea-label {{
  fill: var(--hud); font-family: "Orbitron HUD", Menlo, monospace; font-weight: 700;
  font-size: 9.5px; letter-spacing: 0.14em; text-transform: uppercase; opacity: 0.65;
  text-anchor: middle; text-shadow: 0 0 5px var(--hud-dim);
}}
.land-label {{
  fill: var(--hud); font-family: "Orbitron HUD", Menlo, monospace; font-weight: 700; font-size: 8px;
  letter-spacing: 0.1em; text-transform: uppercase; text-anchor: middle; opacity: 0.72;
  text-shadow: 0 0 4px var(--hud-dim);
}}
/* The choropleth data itself glows too, not just the acquisition HUD —
   a soft warm halo (not cyan: this is data/target territory, same
   red-family logic as the flag) so the governorate colors read as part
   of the instrument rather than a flat web-dashboard layer dropped on
   top of it. */
/* #dataLayer (the group, not each path) carries the pulsing ambient
   glow — putting the animation on individual path.region elements fought
   with their own hover/selected filter changes (an infinite animation on
   `filter` keeps overriding whatever a more specific selector sets), so
   hover/selected stay static and instant while the whole choropleth
   breathes together underneath them. */
#dataLayer {{
  filter: drop-shadow(0 0 3px rgba(220,120,60,0.45));
  animation: radarGlowPulse 2.6s ease-in-out infinite;
}}
path.region {{
  stroke: rgba(5,7,11,0.6); stroke-width: 0.6; cursor: pointer;
  transition: filter 120ms ease, stroke 120ms ease;
}}
path.region:hover {{ filter: brightness(1.35) drop-shadow(0 0 4px var(--gold)); stroke: var(--gold); stroke-width: 1; }}
path.region.selected {{ filter: brightness(1.15) drop-shadow(0 0 5px var(--gold)); stroke: var(--gold); stroke-width: 1.4; }}
#countryOutline {{
  fill: none; stroke: rgba(212,169,74,0.65); stroke-width: 0.9; transition: opacity 300ms ease;
  animation: outlineGlowPulse 2.6s ease-in-out infinite;
}}
@keyframes radarGlowPulse {{
  0%, 100% {{ filter: drop-shadow(0 0 3px rgba(220,120,60,0.45)); }}
  50% {{ filter: drop-shadow(0 0 10px rgba(220,120,60,0.85)); }}
}}
@keyframes outlineGlowPulse {{
  0%, 100% {{ filter: drop-shadow(0 0 3px rgba(212,169,74,0.5)); }}
  50% {{ filter: drop-shadow(0 0 11px rgba(212,169,74,0.95)); }}
}}

/* Tunisia itself glows too (the country shape, the disc, the crescent,
   the star) — simple, low-point-count geometry, so a proper filter here
   is cheap even though it wasn't on the coastline above. Red, not cyan:
   this is the target, not the instrument reading it. Pulses continuously
   like a radar contact, not just a static drop-shadow — that "static"
   version was too subtle to register as "glowing" at all. */
#flagLayer {{ animation: flagGlowPulse 2.6s ease-in-out infinite; }}
@keyframes flagGlowPulse {{
  0%, 100% {{ filter: drop-shadow(0 0 3px var(--red)) drop-shadow(0 0 9px var(--red-glow)); }}
  50% {{ filter: drop-shadow(0 0 7px var(--red)) drop-shadow(0 0 22px var(--red-glow)); }}
}}

/* Acquisition HUD: crosshair + expanding rings + a rotating sweep beam,
   all centered on Tunisia and all in --hud cyan rather than the brand red
   (red is reserved for Tunisia itself and the data layer — this is
   "instrument", not "flag") — a cockpit/targeting-computer read on the
   country before the choropleth data locks in. Fades out via revealP in
   JS once the data layer takes over, same as flagLayer. Glow is applied
   per-element (not once on the whole group) so it lands on the thin rings/
   lines without also blurring the readout text into mush. */
.radar-ring {{
  fill: none; stroke: var(--hud); stroke-width: 0.6; opacity: 0;
  filter: drop-shadow(0 0 1.5px var(--hud));
  transform-box: fill-box; transform-origin: center;
  animation: radarPulse 7s cubic-bezier(0.15, 0.55, 0.4, 1) infinite;
}}
.radar-ring:nth-child(2) {{ animation-delay: 2.33s; }}
.radar-ring:nth-child(3) {{ animation-delay: 4.66s; }}
@keyframes radarPulse {{
  0% {{ transform: scale(0.35); opacity: 0.7; }}
  70% {{ opacity: 0.14; }}
  100% {{ transform: scale(26); opacity: 0; }}
}}
.radar-sweep {{
  animation: radarSpin 5s linear infinite;
  filter: drop-shadow(0 0 1.5px var(--hud));
}}
@keyframes radarSpin {{ to {{ transform: rotate(360deg); }} }}
.crosshair {{
  stroke: var(--hud); fill: none; stroke-width: 0.55; opacity: 0.85;
  filter: drop-shadow(0 0 1.5px var(--hud));
}}
.hud-readout {{
  fill: var(--hud); font-family: "Orbitron HUD", Menlo, monospace; font-weight: 600; font-size: 6.4px;
  letter-spacing: 0.07em; opacity: 0.88; text-shadow: 0 0 4px var(--hud-dim);
  /* A rare, brief stutter — signal-interference flavor, not constant
     noise. 7s cycle, glitching for well under a second of it, so it reads
     as an occasional interruption instead of a distracting tic. */
  animation: hudGlitch 7s ease-in-out infinite;
}}
@keyframes hudGlitch {{
  0%, 91%, 100% {{ transform: translate(0,0); opacity: 0.88; }}
  92% {{ transform: translate(-0.7px, 0.3px); opacity: 0.35; }}
  93% {{ transform: translate(0.6px, -0.2px); opacity: 0.95; }}
  94% {{ transform: translate(-0.3px, 0.15px); opacity: 0.5; }}
  95% {{ transform: translate(0,0); opacity: 0.88; }}
}}

.map-topbar {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 7;
  display: flex; align-items: center; justify-content: space-between;
  padding: 22px 34px; border-bottom: 1px solid var(--hud-dim);
  background: linear-gradient(to bottom, var(--bg) 60%, transparent);
  opacity: 0; pointer-events: none; transition: opacity 200ms ease;
}}
.map-topbar.show {{ opacity: 1; }}
.brand, .theme-switch {{ pointer-events: auto; }}
.brand {{ display: flex; align-items: center; gap: 12px; }}
.brand img {{ width: 24px; height: auto; opacity: 0.9; filter: drop-shadow(0 0 3px var(--hud-dim)); }}
.brand-text {{
  font-family: "Orbitron HUD", monospace; font-weight: 600; font-size: 12px; letter-spacing: 0.16em;
  text-transform: uppercase; color: var(--hud); text-shadow: 0 0 6px var(--hud-dim);
}}
.theme-switch {{
  display: flex; gap: 6px; background: rgba(9,22,26,0.6); border: 1px solid var(--hud-dim);
  border-radius: 10px; padding: 4px; box-shadow: 0 0 12px rgba(75,232,255,0.08);
}}
.theme-btn {{
  font-family: "Orbitron HUD", monospace; font-size: 12px; font-weight: 600; color: var(--ink-2);
  background: transparent; border: none; border-radius: 7px; padding: 8px 16px; cursor: pointer;
  transition: all 150ms ease; letter-spacing: 0.05em; text-transform: uppercase;
}}
.theme-btn.active {{ background: var(--red); color: #fff; box-shadow: 0 0 14px var(--red-glow); }}
.theme-btn:not(.active):hover {{ color: var(--hud); }}

.legend {{
  position: fixed; left: 34px; bottom: 28px; z-index: 4; display: flex; flex-direction: column; gap: 8px;
  font-family: "Orbitron HUD", monospace; font-size: 10px; color: var(--ink-3);
  opacity: 0; transition: opacity 200ms ease; pointer-events: none;
  background: rgba(9,22,26,0.55); border: 1px solid var(--hud-dim); border-radius: 8px;
  padding: 12px 16px; backdrop-filter: blur(6px);
}}
.legend.show {{ opacity: 1; }}
.legend-title {{ color: var(--hud); text-transform: uppercase; letter-spacing: 0.12em; font-size: 10px; text-shadow: 0 0 5px var(--hud-dim); }}
.legend-ramp {{
  width: 180px; height: 6px; border-radius: 3px; background: linear-gradient(to right, #2a0a0d, #701620, #c71f1f, #ff6a2e);
  box-shadow: 0 0 8px rgba(231,0,19,0.35);
}}
.legend-range {{ display: flex; justify-content: space-between; width: 180px; color: var(--ink-2); }}

/* Country-wide KPI strip — real bordered cards docked right under the
   topbar, front and center over the map, not a subtle corner readout.
   Frosted-glass dark cards with a red accent edge so they read clearly
   against whichever governorate colors are underneath. */
.kpi-strip {{
  position: fixed; top: 78px; left: 50%; transform: translateX(-50%); z-index: 4;
  display: grid; gap: 10px; justify-content: center;
  opacity: 0; transition: opacity 200ms ease; pointer-events: none;
}}
.kpi-strip.show {{ opacity: 1; }}
.kpi-card {{
  background: rgba(9,17,22,0.8); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
  border: 1px solid var(--hud-dim); border-left: 3px solid var(--red);
  border-radius: 9px; padding: 10px 20px; min-width: 140px;
  box-shadow: 0 6px 24px rgba(0,0,0,0.35), 0 0 14px rgba(75,232,255,0.06);
}}
.kpi-card-label {{
  font-family: "Orbitron HUD", monospace; font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase;
  color: var(--hud); opacity: 0.75; margin-bottom: 5px;
}}
.kpi-card-value {{
  font-family: "Orbitron HUD", monospace; font-weight: 700; font-size: 21px; color: var(--ink);
  font-variant-numeric: tabular-nums; white-space: nowrap;
}}
.kpi-card-value .unit {{ font-size: 10px; color: var(--ink-2); font-weight: 400; margin-left: 4px; }}
.kpi-card-value .sub {{ display: block; font-family: "Orbitron HUD", monospace; font-size: 11px; font-weight: 400; color: var(--gold); margin-top: 2px; }}

.map-tooltip {{
  position: fixed; pointer-events: none; background: var(--bg-3); border: 1px solid var(--border);
  color: var(--ink); font-size: 12px; padding: 7px 11px; border-radius: 7px; opacity: 0;
  transition: opacity 100ms ease; transform: translate(-50%,-130%); white-space: nowrap; z-index: 6;
}}
.map-tooltip.show {{ opacity: 1; }}
.map-tooltip .u {{ color: var(--ink-2); margin-left: 5px; }}

.panel {{
  position: fixed; top: 0; right: 0; height: 100%; width: 460px; z-index: 5;
  background: var(--bg-2); border-left: 1px solid var(--hud-dim);
  box-shadow: -8px 0 30px rgba(75,232,255,0.05);
  transform: translateX(100%); transition: transform 260ms cubic-bezier(.2,.8,.2,1);
  overflow-y: auto;
}}
.panel.open {{ transform: translateX(0); }}
.panel-banner {{
  position: relative; width: 100%; height: 340px; background-size: cover; background-position: center;
}}
.panel-banner::after {{
  content: ''; position: absolute; inset: 0;
  background: linear-gradient(180deg, rgba(11,15,22,0.25) 0%, rgba(11,15,22,0.35) 45%, var(--bg-2) 96%);
}}
.panel-monument-credit {{
  position: absolute; left: 16px; bottom: 8px; z-index: 1; font-size: 9.5px; color: rgba(238,241,246,0.75);
  letter-spacing: 0.02em; max-width: 300px; line-height: 1.4;
}}
.panel-monument-credit b {{ display: block; font-size: 11px; color: #fff; font-weight: 600; margin-bottom: 1px; }}
.panel-close {{
  position: absolute; top: 14px; right: 14px; z-index: 2; width: 28px; height: 28px; border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.25); background: rgba(11,15,22,0.55); backdrop-filter: blur(2px);
  color: #fff; cursor: pointer; font-size: 14px; line-height: 1;
}}
.panel-close:hover {{ border-color: var(--hud); color: var(--hud); }}
.panel-content {{ padding: 20px 28px 30px; }}
.panel-name-ar {{ font-size: 24px; margin-bottom: 4px; color: var(--hud); text-shadow: 0 0 8px var(--hud-dim); }}
.panel-name-en {{
  font-family: "Orbitron HUD", monospace; font-weight: 700; font-size: 26px; line-height: 1.1;
  text-shadow: 0 0 10px var(--hud-dim);
}}
.panel-name-fr {{
  font-family: "Orbitron HUD", monospace; font-size: 11.5px; color: var(--hud); letter-spacing: 0.1em;
  text-transform: uppercase; margin-top: 6px; opacity: 0.8;
}}
.panel-about {{ margin-top: 16px; font-size: 13px; line-height: 1.65; color: var(--ink-2); }}
.panel-kpi {{ margin-top: 22px; padding-top: 20px; border-top: 1px solid var(--hud-dim); }}
.panel-kpi-label {{
  font-family: "Orbitron HUD", monospace; font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--hud); opacity: 0.75; margin-bottom: 6px;
}}
.panel-kpi-value {{
  font-family: "Orbitron HUD", monospace; font-weight: 700; font-size: 36px; color: var(--red);
  text-shadow: 0 0 12px var(--red-glow);
}}
.panel-kpi-unit {{ font-size: 13px; color: var(--ink-2); margin-left: 6px; }}
.panel-rank {{ font-family: "Orbitron HUD", monospace; font-size: 10.5px; color: var(--hud); opacity: 0.8; margin-top: 8px; }}
.panel-insight {{ margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--hud-dim); font-size: 13px; line-height: 1.65; color: var(--ink-2); }}
.panel-insight-label {{
  font-family: "Orbitron HUD", monospace; font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--hud); opacity: 0.75; margin-bottom: 8px;
}}
.panel-note {{ margin-top: 22px; font-size: 11px; line-height: 1.6; color: var(--ink-3); }}

.credits {{
  position: relative; z-index: 3; background: var(--bg); padding: 60px 34px;
  border-top: 1px solid var(--hud-dim); font-size: 12.5px; color: var(--ink-3); line-height: 1.7;
}}
.credits b {{ font-family: "Orbitron HUD", monospace; letter-spacing: 0.04em; color: var(--hud); }}
</style>

<div class="terminal-intro" id="terminalIntro">
  <div class="terminal-title">
    <img class="coat" src="data:image/svg+xml;base64,{coat_b64}" alt="Coat of arms of Tunisia" />
    <div class="terminal-title-en">TUNISIA</div>
    <div class="terminal-title-tag">in numbers</div>
    <div class="terminal-subline">
      <span class="fr">Tunisie</span>
      <span class="ar">تونس</span>
    </div>
  </div>
  <div class="terminal-guide">
    <svg class="pacman" viewBox="0 0 100 110" xmlns="http://www.w3.org/2000/svg">
      <path class="chechia" d="M 27,30 L 32,9 L 68,9 L 73,30 Q 50,21 27,30 Z"/>
      <circle class="chechia-tassel" cx="50" cy="9" r="3"/>
      <circle class="pacman-head" cx="50" cy="60" r="42"/>
      <circle class="pacman-eye" cx="58" cy="34" r="5"/>
      <polygon class="jaw jaw-top" points="50,60 94,60 94,45"/>
      <polygon class="jaw jaw-bottom" points="50,60 94,60 94,75"/>
    </svg>
    <div class="terminal-lines" id="terminalLines"></div>
  </div>
  <div class="terminal-hint" id="terminalHint">Scroll to begin<span class="chevron"></span></div>
</div>
<div class="scroll-spacer">
  <div class="hero" id="hero">
    <div class="map-canvas-wrap">
      <svg class="atlas-map" id="atlasSvg" viewBox="{FULL_VIEWBOX[0]} {FULL_VIEWBOX[1]} {FULL_VIEWBOX[2]} {FULL_VIEWBOX[3]}" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <clipPath id="countryClip"><path d="{COUNTRY_PATH}"/></clipPath>
          <radialGradient id="seaGradient" cx="42%" cy="38%" r="85%">
            <stop offset="0%" stop-color="#081824"/>
            <stop offset="45%" stop-color="#050f18"/>
            <stop offset="100%" stop-color="#02070c"/>
          </radialGradient>
          <pattern id="hudGrid" width="54" height="54" patternUnits="userSpaceOnUse">
            <path d="M 54 0 L 0 0 0 54" fill="none" stroke="var(--hud)" stroke-width="0.3"/>
          </pattern>
        </defs>
        <rect x="{FULL_VIEWBOX[0]}" y="{FULL_VIEWBOX[1]}" width="{FULL_VIEWBOX[2]}" height="{FULL_VIEWBOX[3]}" fill="url(#seaGradient)"/>
        <rect class="hud-grid" x="{FULL_VIEWBOX[0]}" y="{FULL_VIEWBOX[1]}" width="{FULL_VIEWBOX[2]}" height="{FULL_VIEWBOX[3]}" fill="url(#hudGrid)"/>
        <text class="sea-label" x="{W*0.74}" y="{H*0.44}">MEDITERRANEAN SEA</text>
        <path class="land-fill" d="{OTHER_LAND_PATH}"/>
        <path class="land-glow" d="{OTHER_LAND_PATH}"/>
        {"".join(f'<text class="land-label" x="{lbl["x"]}" y="{lbl["y"]}">{lbl["name"]}</text>' for lbl in LAND_LABELS)}
        <g id="flagLayer" clip-path="url(#countryClip)">
          <path d="{COUNTRY_PATH}" fill="#c8102e"/>
          <circle cx="{flag_cx}" cy="{flag_cy}" r="{flag_r}" fill="#fdfdfb"/>
          <circle cx="{flag_cx}" cy="{flag_cy}" r="{crescent_outer_r}" fill="#c8102e"/>
          <circle cx="{flag_cx + crescent_offset}" cy="{flag_cy}" r="{crescent_inner_r}" fill="#fdfdfb"/>
          <polygon points="{STAR_PTS}" fill="#c8102e"/>
        </g>
        <g id="acquisitionHud">
          <circle class="radar-ring" cx="{flag_cx}" cy="{flag_cy}" r="{RING_BASE_R}"/>
          <circle class="radar-ring" cx="{flag_cx}" cy="{flag_cy}" r="{RING_BASE_R}"/>
          <circle class="radar-ring" cx="{flag_cx}" cy="{flag_cy}" r="{RING_BASE_R}"/>
          {RADAR_SWEEP_SVG}
          <g class="crosshair">
            <circle cx="{flag_cx}" cy="{flag_cy}" r="{CROSSHAIR_R}"/>
            <line x1="{flag_cx-CROSSHAIR_TICK}" y1="{flag_cy}" x2="{flag_cx-CROSSHAIR_R}" y2="{flag_cy}"/>
            <line x1="{flag_cx+CROSSHAIR_R}" y1="{flag_cy}" x2="{flag_cx+CROSSHAIR_TICK}" y2="{flag_cy}"/>
            <line x1="{flag_cx}" y1="{flag_cy-CROSSHAIR_TICK}" x2="{flag_cx}" y2="{flag_cy-CROSSHAIR_R}"/>
            <line x1="{flag_cx}" y1="{flag_cy+CROSSHAIR_R}" x2="{flag_cx}" y2="{flag_cy+CROSSHAIR_TICK}"/>
          </g>
          <text class="hud-readout" x="{flag_cx+CROSSHAIR_TICK+4}" y="{flag_cy-6}">TN · REPUBLIC OF TUNISIA</text>
          <text class="hud-readout" x="{flag_cx+CROSSHAIR_TICK+4}" y="{flag_cy+4}">{COORD_READOUT}</text>
        </g>
        <g id="dataLayer" clip-path="url(#countryClip)" opacity="0">
          {"".join(f'<path class="region" data-gov="{g}" d="{d}"></path>' for g, d in GOV_PATHS.items())}
        </g>
        <path id="countryOutline" d="{COUNTRY_PATH}"/>
      </svg>
    </div>
    <div class="locator show" id="locator">
      <svg viewBox="0 0 {africa["viewbox_w"]} {africa["viewbox_h"]}" xmlns="http://www.w3.org/2000/svg">
        <path d="{africa["africa_path"]}" fill="var(--land)" stroke="rgba(212,169,74,0.5)" stroke-width="0.6"/>
        <circle cx="{africa["tunisia_x"]}" cy="{africa["tunisia_y"]}" r="3" fill="var(--red)" stroke="#fff" stroke-width="1"/>
      </svg>
      <div class="locator-label">Tunisia in Africa</div>
    </div>
  </div>
</div>

<div class="map-topbar" id="topbar">
  <div class="brand"><img src="data:image/svg+xml;base64,{coat_b64}" alt="" /><span class="brand-text">Tunisia Data Atlas</span></div>
  <div class="theme-switch" id="themeSwitch">
    <button class="theme-btn active" data-theme="population">Population</button>
    <button class="theme-btn" data-theme="economy">Economy</button>
    <button class="theme-btn" data-theme="health">Health &amp; Education</button>
  </div>
</div>
<div class="kpi-strip" id="kpiStrip"></div>
<div class="legend" id="legend">
  <div class="legend-title" id="legendTitle">Natalité</div>
  <div class="legend-ramp"></div>
  <div class="legend-range"><span id="legendLo">-</span><span id="legendHi">-</span></div>
</div>
<div class="map-tooltip" id="mapTooltip"></div>
<div class="panel" id="panel">
  <div class="panel-banner" id="panelBanner">
    <button class="panel-close" id="panelClose">&times;</button>
    <div class="panel-monument-credit"><b id="panelMonumentName"></b><span id="panelMonumentCredit"></span></div>
  </div>
  <div class="panel-content">
    <div class="panel-name-ar ar" id="panelAr"></div>
    <div class="panel-name-en" id="panelEn"></div>
    <div class="panel-name-fr" id="panelFr"></div>
    <div class="panel-about" id="panelAbout"></div>
    <div class="panel-kpi">
      <div class="panel-kpi-label" id="panelKpiLabel">—</div>
      <div><span class="panel-kpi-value" id="panelKpiValue">—</span><span class="panel-kpi-unit" id="panelKpiUnit"></span></div>
      <div class="panel-rank" id="panelRank"></div>
    </div>
    <div class="panel-insight">
      <div class="panel-insight-label">At a glance</div>
      <div id="panelInsight"></div>
    </div>
    <div class="panel-note">Figures from the INS data portal via this project's own pipeline. No published study is
    linked to this indicator yet — the note above is computed directly from the data, not an external citation.</div>
  </div>
</div>

<div class="credits">
  <b>Tunisia Data Atlas</b><br/>
  Governorate boundaries: TUN_adm1 shapefile. Mediterranean-basin coastlines (Iberia to Turkey, the
  Atlas mountains to the Sahara): Natural Earth (public domain, 10m).
  National emblem: Wikimedia Commons, public domain.<br/>
  Each governorate panel shows one real, verified monument photo (Wikimedia Commons, freely licensed, credited
  in-panel) and a description condensed from that governorate's English Wikipedia article. Where a governorate
  has no single iconic built landmark, the closest real, well-documented site was used instead of inventing one.
</div>

<script>
const PAYLOAD = {json.dumps(PAYLOAD, ensure_ascii=False)};
const FULL_VB = {json.dumps(FULL_VIEWBOX)};
const TUNISIA_VB = {json.dumps(TUNISIA_VIEWBOX)};

// Boot-sequence typewriter: Ammar (the chomping mascot) "speaks" this
// into the dark, mapless first screen, then reveals a scroll hint. Runs
// once on load, entirely independent of the scroll-driven zoom below.
const terminalIntro = document.getElementById('terminalIntro');
const terminalLines = document.getElementById('terminalLines');
const terminalHint = document.getElementById('terminalHint');
const BOOT_LINES = [
  "HI, I'M AMMAR.",
  "I'LL BE YOUR GUIDE THROUGH TUNISIA'S DATA ATLAS —",
  'POPULATION, ECONOMY, AND HEALTH, BY GOVERNORATE.',
  "LET'S TAKE A LOOK.",
];
(function typeBootSequence() {{
  let li = 0, ci = 0;
  function tick() {{
    if (li >= BOOT_LINES.length) {{
      terminalHint.classList.add('show');
      return;
    }}
    let lineEl = document.getElementById('tline-' + li);
    if (!lineEl) {{
      lineEl = document.createElement('div');
      lineEl.className = 'terminal-line';
      lineEl.id = 'tline-' + li;
      terminalLines.appendChild(lineEl);
    }}
    const full = BOOT_LINES[li];
    lineEl.innerHTML = full.slice(0, ci) + '<span class="terminal-cursor"></span>';
    if (ci < full.length) {{
      ci++;
      setTimeout(tick, 28 + Math.random() * 40);
    }} else {{
      li++; ci = 0;
      setTimeout(tick, 480);
    }}
  }}
  setTimeout(tick, 550);
}})();

const spacer = document.querySelector('.scroll-spacer');
const svg = document.getElementById('atlasSvg');
const flagLayer = document.getElementById('flagLayer');
const acquisitionHud = document.getElementById('acquisitionHud');
const dataLayer = document.getElementById('dataLayer');
const countryOutline = document.getElementById('countryOutline');
const topbar = document.getElementById('topbar');
const legend = document.getElementById('legend');

function lerp(a, b, t) {{ return a + (b - a) * t; }}
// Zoom is perceived as a RATIO, not a pixel distance — halving the visible
// width always reads as "one zoom level" whether you're going from 1000px
// to 500px or from 40px to 20px. Interpolating viewBox width/height
// linearly (plain lerp) made equal scroll distance cover wildly unequal
// PERCEIVED zoom: barely anything happened for the first couple of scroll
// ticks, then almost the entire zoom rushed through in the next one. This
// interpolates width/height exponentially (equal ratio per equal t) and
// keeps the center point moving smoothly, which is the standard way map
// libraries (Leaflet/Mapbox) handle zoom-level transitions.
function expLerp(a, b, t) {{ return a * Math.pow(b / a, t); }}
function easeInOut(t) {{ return t < 0.5 ? 2*t*t : 1 - Math.pow(-2*t+2, 2)/2; }}

const FULL_CX = FULL_VB[0] + FULL_VB[2]/2, FULL_CY = FULL_VB[1] + FULL_VB[3]/2;
const TUNISIA_CX = TUNISIA_VB[0] + TUNISIA_VB[2]/2, TUNISIA_CY = TUNISIA_VB[1] + TUNISIA_VB[3]/2;
// Width and height used to be expLerp'd independently. Both curves hit
// their own endpoints correctly, but FULL_VB is wide (aspect ~1.4) and
// TUNISIA_VB is tall (aspect ~0.46) — two very different ratios — so
// interpolating them separately let the IN-BETWEEN aspect ratio wander
// wherever the two independent curves happened to cross, which turned out
// to swing through something close to square around the midpoint. That's
// what made the country look "fat" mid-zoom: not a projection error (fixed
// separately in build_atlas_geo.py), but the viewBox itself briefly
// showing a squashed window. Deriving height from width and a directly-
// interpolated aspect ratio guarantees the aspect moves monotonically
// from FULL_VB's to TUNISIA_VB's, with no overshoot in between.
const FULL_ASPECT = FULL_VB[2] / FULL_VB[3], TUNISIA_ASPECT = TUNISIA_VB[2] / TUNISIA_VB[3];

function onScroll() {{
  // The terminal boot screen isn't sticky — it's a normal block sitting
  // before .scroll-spacer, so it scrolls away on its own. What it DOES
  // need is for the map's zoom math below to ignore however many pixels
  // of scroll it took to get past it; otherwise the zoom would already be
  // partway done by the time the map even becomes visible.
  const introH = terminalIntro.offsetHeight;
  terminalIntro.style.opacity = String(Math.max(0, 1 - window.scrollY / (introH * 0.8)));
  const effectiveScrollY = Math.max(0, window.scrollY - introH);

  const releaseScroll = spacer.offsetHeight - window.innerHeight;
  const p = Math.max(0, Math.min(1, effectiveScrollY / (releaseScroll * 0.92)));
  // Zoom now uses the entire scroll range (was p/0.75, which finished the
  // whole zoom in ~4 scroll ticks and then left 25% of the scroll as dead
  // space before the UI reveal even started). Reveal is now a short overlay
  // near the very end instead of a separate late-scroll phase.
  // No easing curve here on top of the exponential width scaling — an
  // S-curve easing plus an already-exponential zoom compound into an even
  // steeper middle section, which is the opposite of what's needed. Plain
  // linear p, paired with expLerp above, is what actually gives an even
  // ratio-per-scroll-tick feel.
  const zoomP = p;
  const revealP = Math.max(0, Math.min(1, (p - 0.86) / 0.14));

  const vbW = expLerp(FULL_VB[2], TUNISIA_VB[2], zoomP);
  const vbH = vbW / expLerp(FULL_ASPECT, TUNISIA_ASPECT, zoomP);
  const cx = lerp(FULL_CX, TUNISIA_CX, zoomP);
  const cy = lerp(FULL_CY, TUNISIA_CY, zoomP);
  const vb = [cx - vbW/2, cy - vbH/2, vbW, vbH];
  svg.setAttribute('viewBox', vb.join(' '));

  document.getElementById('locator').style.opacity = String(Math.max(0, 1 - p / 0.2));

  flagLayer.setAttribute('opacity', String(1 - revealP));
  acquisitionHud.setAttribute('opacity', String(1 - revealP));
  dataLayer.setAttribute('opacity', String(revealP));
  countryOutline.style.opacity = String(0.3 + revealP*0.7);

  const uiVisible = p > 0.93;
  topbar.classList.toggle('show', uiVisible);
  legend.classList.toggle('show', uiVisible);
  document.getElementById('kpiStrip').classList.toggle('show', uiVisible);
}}
window.addEventListener('scroll', onScroll, {{ passive: true }});
onScroll();

let currentTheme = 'population';
const tooltip = document.getElementById('mapTooltip');
const RAMP = ['#2a0a0d','#4a1015','#701620','#9c1a1f','#c71f1f','#e63c22','#ff6a2e'];

// Plain linear (v-lo)/(hi-lo) crushes anything skewed — e.g. bank branch
// counts (15 to 467: Tunis alone is ~30x the smallest governorate) puts
// every governorate except Tunis in the same one or two darkest ramp
// steps, reading as "one bright outlier, everything else identical"
// rather than real variation. Once max/min crosses a 5x ratio, switch to
// a rank/quantile scale instead: each governorate's color reflects its
// RANK among all 24, not its raw distance from the extremes, so the ramp
// always spreads across the full range of governorates regardless of how
// skewed the underlying counts are. Rate-like indicators (birth rate,
// hospital beds per 1,000) rarely hit that ratio and keep the linear
// scale, which is the more honest read when the range is already narrow.
function colorFor(v, sortedValues, lo, hi, skewed) {{
  if (hi <= lo) return RAMP[Math.floor(RAMP.length/2)];
  let t;
  if (skewed) {{
    t = sortedValues.findIndex(x => x >= v) / (sortedValues.length - 1);
  }} else {{
    t = (v - lo) / (hi - lo);
  }}
  return RAMP[Math.max(0, Math.min(RAMP.length-1, Math.round(t * (RAMP.length-1))))];
}}

function paintMap() {{
  const theme = PAYLOAD.themes[currentTheme];
  const d = PAYLOAD.data[theme.slug];
  const values = Object.values(d.values);
  const lo = Math.min(...values), hi = Math.max(...values);
  const skewed = lo > 0 && (hi / lo) > 5;
  const sortedValues = skewed ? [...values].sort((a, b) => a - b) : null;
  document.getElementById('legendTitle').textContent = d.label + ' · ' + d.year + (skewed ? ' (by rank)' : '');
  document.getElementById('legendLo').textContent = lo.toLocaleString();
  document.getElementById('legendHi').textContent = hi.toLocaleString();
  dataLayer.querySelectorAll('.region').forEach(function(el) {{
    const v = d.values[el.dataset.gov];
    el.setAttribute('fill', v !== undefined ? colorFor(v, sortedValues, lo, hi, skewed) : '#1a1f29');
    el.dataset.value = v !== undefined ? v : '';
  }});
}}
paintMap();

const kpiStrip = document.getElementById('kpiStrip');
function paintStats() {{
  const cards = PAYLOAD.nationalStats[currentTheme] || [];
  // Fixed column count (not auto-fill/flex-wrap) so a partial last row lines
  // up under the grid's own tracks instead of being independently centered
  // under the full viewport width — that's what made a lone wrapped card
  // float in the middle of the map before.
  const cols = Math.min(cards.length, 5) || 1;
  kpiStrip.style.gridTemplateColumns = 'repeat(' + cols + ', 154px)';
  kpiStrip.innerHTML = cards.map(function(c) {{
    let valueHtml;
    if (c.value === null) {{
      valueHtml = '—';
    }} else if (typeof c.value === 'string') {{
      // max_gov card: value is a governorate name, sub is its number
      const name = PAYLOAD.trilingual[c.value];
      valueHtml = (name ? name.en : c.value) + '<span class="sub">' + c.sub.toLocaleString() + ' ' + c.unit + '</span>';
    }} else {{
      valueHtml = c.value.toLocaleString() + (c.unit ? '<span class="unit">' + c.unit + '</span>' : '');
    }}
    return '<div class="kpi-card"><div class="kpi-card-label">' + c.label +
      '</div><div class="kpi-card-value">' + valueHtml + '</div></div>';
  }}).join('');
}}
paintStats();

document.getElementById('themeSwitch').addEventListener('click', function(e) {{
  const btn = e.target.closest('.theme-btn');
  if (!btn) return;
  currentTheme = btn.dataset.theme;
  document.querySelectorAll('.theme-btn').forEach(function(b) {{ b.classList.toggle('active', b === btn); }});
  paintMap();
  paintStats();
  if (panelOpenGov) openPanel(panelOpenGov);
}});

dataLayer.querySelectorAll('.region').forEach(function(el) {{
  el.addEventListener('mousemove', function(e) {{
    tooltip.style.left = e.clientX + 'px';
    tooltip.style.top = e.clientY + 'px';
    const name = PAYLOAD.trilingual[el.dataset.gov];
    const v = el.dataset.value;
    tooltip.innerHTML = (name ? name.en : el.dataset.gov) + (v ? '<span class="u">' + v + '</span>' : '');
    tooltip.classList.add('show');
  }});
  el.addEventListener('mouseleave', function() {{ tooltip.classList.remove('show'); }});
  el.addEventListener('click', function() {{ openPanel(el.dataset.gov); }});
}});

let panelOpenGov = null;
const panel = document.getElementById('panel');

function openPanel(gov) {{
  panelOpenGov = gov;
  const name = PAYLOAD.trilingual[gov] || {{ar: '', en: gov, fr: gov}};
  document.getElementById('panelAr').textContent = name.ar;
  document.getElementById('panelEn').textContent = name.en;
  document.getElementById('panelFr').textContent = name.fr;

  const mon = PAYLOAD.monuments[gov];
  const banner = document.getElementById('panelBanner');
  if (mon) {{
    banner.style.backgroundImage = 'linear-gradient(180deg, rgba(11,15,22,0.05), rgba(11,15,22,0.05)), url(data:image/jpeg;base64,' + mon.b64 + ')';
    document.getElementById('panelMonumentName').textContent = mon.name;
    document.getElementById('panelMonumentCredit').textContent = ' — ' + mon.credit;
  }}
  document.getElementById('panelAbout').textContent = PAYLOAD.text[gov] || '';

  const theme = PAYLOAD.themes[currentTheme];
  const d = PAYLOAD.data[theme.slug];
  const entries = Object.entries(d.values).sort(function(a,b) {{ return b[1]-a[1]; }});
  const idx = entries.findIndex(function(e) {{ return e[0] === gov; }});
  const value = d.values[gov];
  const values = Object.values(d.values);
  const avg = values.reduce(function(a,b) {{ return a+b; }}, 0) / values.length;

  document.getElementById('panelKpiLabel').textContent = d.label + ' (' + d.year + ')';
  document.getElementById('panelKpiValue').textContent = value !== undefined ? value.toLocaleString() : '—';
  document.getElementById('panelKpiUnit').textContent = theme.unit;
  document.getElementById('panelRank').textContent = idx >= 0 ? ('Rank ' + (idx+1) + ' of ' + entries.length + ' governorates') : '';

  let insight = 'No data for this indicator in this governorate.';
  if (value !== undefined) {{
    const diff = ((value - avg) / avg * 100);
    const dir = diff >= 0 ? 'above' : 'below';
    insight = name.en + ' records ' + value.toLocaleString() + ' ' + theme.unit + ' — ' +
      Math.abs(diff).toFixed(0) + '% ' + dir + ' the 24-governorate average of ' + avg.toFixed(1) + '.';
  }}
  document.getElementById('panelInsight').textContent = insight;

  dataLayer.querySelectorAll('.region').forEach(function(el) {{ el.classList.toggle('selected', el.dataset.gov === gov); }});
  panel.classList.add('open');
}}

document.getElementById('panelClose').addEventListener('click', function() {{
  panel.classList.remove('open');
  panelOpenGov = null;
  dataLayer.querySelectorAll('.region').forEach(function(el) {{ el.classList.remove('selected'); }});
}});
</script>
'''
    return html
