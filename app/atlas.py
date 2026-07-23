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
        "coat_b64": (ASSETS_DIR / "coat_of_arms.b64").read_text().strip(),
        "mediterranean_b64": _b64(ASSETS_DIR / "hero" / "mediterranean.jpg"),
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
    coat_b64 = assets["coat_b64"]
    mediterranean_b64 = assets["mediterranean_b64"]
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
}}

* {{ box-sizing: border-box; }}
/* no overflow-x:hidden here — setting only overflow-x on body forces
   overflow-y to compute as auto per the CSS overflow spec, which breaks
   position:sticky for every sticky element on the page. Nothing here
   actually overflows horizontally (everything is width:100%/inset:0), so
   there's nothing to clip in the first place. */
html, body {{ margin: 0; padding: 0; background: var(--bg); }}
body {{ font-family: "El Messiri", -apple-system, BlinkMacSystemFont, sans-serif; color: var(--ink); }}
[lang="ar"], .ar {{ direction: rtl; }}

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
.hero-scrim {{
  position: absolute; inset: 0; z-index: 2; pointer-events: none;
  /* Lighter and faster-fading than before — the old version stayed 90%+
     opaque through the whole top half of the screen, which made the real
     (fully-rendered) map underneath look like it wasn't there at all: a
     hard black block up top rather than a country the viewer could see
     they'd arrived at. The title itself has its own white/red stroke, so
     it doesn't need a near-opaque backdrop to stay legible. */
  background: linear-gradient(180deg, rgba(5,7,11,0.72) 0%, rgba(5,7,11,0.5) 32%, rgba(5,7,11,0.22) 55%, transparent 74%);
  transition: opacity 200ms ease;
}}
.hero-text {{
  position: absolute; top: 8vh; left: 0; right: 0; z-index: 3;
  display: flex; flex-direction: column; align-items: center; text-align: center;
  pointer-events: none; will-change: opacity, transform;
}}
.hero-eyebrow {{ font-family: "El Messiri", sans-serif; font-weight: 600; font-size: 11px; letter-spacing: 0.32em; text-transform: uppercase; color: var(--gold); margin-bottom: 22px; }}
.hero-title-wrap {{ position: relative; display: inline-block; margin: 4px 0 2px; }}
.coat {{
  position: absolute; left: 0; bottom: 100%; margin-bottom: 10px;
  width: 34px; height: auto;
}}
.hero-title-en {{
  font-family: "El Messiri", sans-serif; font-weight: 700;
  font-size: clamp(72px, 15vw, 190px); letter-spacing: 0.01em; line-height: 0.9;
  color: var(--red); -webkit-text-stroke: 2.5px #fff; paint-order: stroke fill;
}}
.hero-title-tag {{
  position: absolute; right: 4px; bottom: -22px;
  font-style: italic; font-size: 16px; color: var(--gold); letter-spacing: 0.02em;
}}
.hero-subline {{
  display: flex; align-items: baseline; justify-content: space-between;
  width: min(300px, 70vw); margin: 30px auto 0;
}}
.hero-subline .fr {{ font-size: 13px; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink-2); text-shadow: 0 1px 10px rgba(2,3,5,0.95), 0 1px 3px rgba(2,3,5,0.95); }}
.hero-subline .ar {{ font-size: 17px; font-weight: 600; color: var(--ink-2); text-shadow: 0 1px 10px rgba(2,3,5,0.95), 0 1px 3px rgba(2,3,5,0.95); }}
.hero-desc {{
  max-width: 460px; margin: 26px auto 0; font-size: 13.5px; line-height: 1.65; color: var(--ink-2);
  padding: 0 24px;
  /* The scrim behind the hero was lightened so the real map reads as
     present right away instead of a black block — that means this text can
     now sit over busier map content (the flag emblem, coastline), so each
     line gets its own dark halo for legibility instead of relying purely on
     the uniform background darkening. */
  text-shadow: 0 1px 10px rgba(2,3,5,0.95), 0 1px 4px rgba(2,3,5,0.95), 0 0 20px rgba(2,3,5,0.7);
}}
.hero-scroll-hint {{
  position: absolute; bottom: 6vh; left: 0; right: 0; z-index: 3; text-align: center;
  font-family: Menlo, monospace; font-size: 10.5px; color: var(--ink-3);
  letter-spacing: 0.18em; text-transform: uppercase;
}}
.hero-scroll-hint .chevron {{
  display: block; margin: 8px auto 0; width: 9px; height: 9px;
  border-right: 1.5px solid var(--ink-3); border-bottom: 1.5px solid var(--ink-3);
  transform: rotate(45deg); animation: bob 1.8s ease-in-out infinite;
}}
@keyframes bob {{ 0%,100% {{ transform: rotate(45deg) translate(0,0); }} 50% {{ transform: rotate(45deg) translate(4px,4px); }} }}

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
.hero-photo {{
  position: absolute; inset: 0; z-index: 3; width: 100%; height: 100%;
  object-fit: cover; object-position: 50% 62%;
  pointer-events: none; will-change: opacity;
}}
svg.atlas-map {{ width: 100%; height: 100%; }}
.land {{ fill: var(--land); stroke: rgba(238,241,246,0.10); stroke-width: 0.6; }}
.sea-label {{ fill: var(--ink-3); font-family: Menlo, monospace; font-size: 5px; letter-spacing: 0.3em; text-transform: uppercase; }}
path.region {{ stroke: rgba(5,7,11,0.6); stroke-width: 0.6; cursor: pointer; transition: filter 120ms ease, stroke 120ms ease; }}
path.region:hover {{ filter: brightness(1.35); stroke: var(--gold); stroke-width: 1; }}
path.region.selected {{ stroke: var(--gold); stroke-width: 1.4; }}
#countryOutline {{ fill: none; stroke: rgba(212,169,74,0.55); stroke-width: 0.9; transition: opacity 300ms ease; }}

.map-topbar {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 7;
  display: flex; align-items: center; justify-content: space-between;
  padding: 22px 34px; border-bottom: 1px solid var(--border);
  background: linear-gradient(to bottom, var(--bg) 60%, transparent);
  opacity: 0; pointer-events: none; transition: opacity 200ms ease;
}}
.map-topbar.show {{ opacity: 1; }}
.brand, .theme-switch {{ pointer-events: auto; }}
.brand {{ display: flex; align-items: center; gap: 12px; }}
.brand img {{ width: 24px; height: auto; opacity: 0.9; }}
.brand-text {{ font-family: "El Messiri", sans-serif; font-weight: 600; font-size: 12.5px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-2); }}
.theme-switch {{ display: flex; gap: 6px; background: var(--bg-2); border: 1px solid var(--border); border-radius: 10px; padding: 4px; }}
.theme-btn {{
  font-family: "El Messiri", sans-serif; font-size: 13.5px; font-weight: 600; color: var(--ink-2);
  background: transparent; border: none; border-radius: 7px; padding: 8px 16px; cursor: pointer;
  transition: all 150ms ease; letter-spacing: 0.02em;
}}
.theme-btn.active {{ background: var(--red); color: #fff; }}
.theme-btn:not(.active):hover {{ color: var(--ink); }}

.legend {{
  position: fixed; left: 34px; bottom: 28px; z-index: 4; display: flex; flex-direction: column; gap: 8px;
  font-family: Menlo, monospace; font-size: 10px; color: var(--ink-3);
  opacity: 0; transition: opacity 200ms ease; pointer-events: none;
}}
.legend.show {{ opacity: 1; }}
.legend-title {{ color: var(--ink-2); text-transform: uppercase; letter-spacing: 0.1em; font-size: 10px; }}
.legend-ramp {{ width: 180px; height: 6px; border-radius: 3px; background: linear-gradient(to right, #2a0a0d, #701620, #c71f1f, #ff6a2e); }}
.legend-range {{ display: flex; justify-content: space-between; width: 180px; }}

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
  background: rgba(11,15,22,0.78); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
  border: 1px solid var(--border); border-left: 3px solid var(--red);
  border-radius: 9px; padding: 10px 20px; min-width: 140px;
  box-shadow: 0 6px 24px rgba(0,0,0,0.35);
}}
.kpi-card-label {{ font-family: Menlo, monospace; font-size: 9.5px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 5px; }}
.kpi-card-value {{ font-family: "El Messiri", sans-serif; font-weight: 700; font-size: 23px; color: var(--ink); font-variant-numeric: tabular-nums; white-space: nowrap; }}
.kpi-card-value .unit {{ font-size: 11px; color: var(--ink-2); font-weight: 400; margin-left: 4px; }}
.kpi-card-value .sub {{ display: block; font-family: Menlo, monospace; font-size: 11px; font-weight: 400; color: var(--gold); margin-top: 2px; }}

.map-tooltip {{
  position: fixed; pointer-events: none; background: var(--bg-3); border: 1px solid var(--border);
  color: var(--ink); font-size: 12px; padding: 7px 11px; border-radius: 7px; opacity: 0;
  transition: opacity 100ms ease; transform: translate(-50%,-130%); white-space: nowrap; z-index: 6;
}}
.map-tooltip.show {{ opacity: 1; }}
.map-tooltip .u {{ color: var(--ink-2); margin-left: 5px; }}

.panel {{
  position: fixed; top: 0; right: 0; height: 100%; width: 460px; z-index: 5;
  background: var(--bg-2); border-left: 1px solid var(--border);
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
.panel-close:hover {{ border-color: var(--gold); color: var(--gold); }}
.panel-content {{ padding: 20px 28px 30px; }}
.panel-name-ar {{ font-size: 22px; margin-bottom: 2px; }}
.panel-name-en {{ font-family: "El Messiri", sans-serif; font-weight: 700; font-size: 30px; line-height: 1.05; }}
.panel-name-fr {{ font-size: 13px; color: var(--ink-2); letter-spacing: 0.05em; margin-top: 4px; }}
.panel-about {{ margin-top: 16px; font-size: 13px; line-height: 1.65; color: var(--ink-2); }}
.panel-kpi {{ margin-top: 22px; padding-top: 20px; border-top: 1px solid var(--border); }}
.panel-kpi-label {{ font-size: 10.5px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 6px; }}
.panel-kpi-value {{ font-family: "El Messiri", sans-serif; font-weight: 700; font-size: 40px; color: var(--red); }}
.panel-kpi-unit {{ font-size: 13px; color: var(--ink-2); margin-left: 6px; }}
.panel-rank {{ font-family: Menlo, monospace; font-size: 11px; color: var(--ink-2); margin-top: 8px; }}
.panel-insight {{ margin-top: 22px; padding-top: 18px; border-top: 1px solid var(--border); font-size: 13px; line-height: 1.65; color: var(--ink-2); }}
.panel-insight-label {{ font-size: 10.5px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 8px; }}
.panel-note {{ margin-top: 22px; font-size: 11px; line-height: 1.6; color: var(--ink-3); }}

.credits {{
  position: relative; z-index: 3; background: var(--bg); padding: 60px 34px;
  border-top: 1px solid var(--border); font-size: 12.5px; color: var(--ink-3); line-height: 1.7;
}}
.credits b {{ color: var(--ink-2); }}
</style>

<div class="scroll-spacer">
  <div class="hero" id="hero">
    <div class="hero-text" id="heroText">
      <div class="hero-eyebrow">Data Atlas</div>
      <div class="hero-title-wrap">
        <img class="coat" src="data:image/svg+xml;base64,{coat_b64}" alt="Coat of arms of Tunisia" />
        <div class="hero-title-en">TUNISIA</div>
        <div class="hero-title-tag">in numbers</div>
      </div>
      <div class="hero-subline">
        <span class="fr">Tunisie</span>
        <span class="ar">تونس</span>
      </div>
      <p class="hero-desc">
        Population, economy, and health, mapped by governorate — built on real data pulled
        from Tunisia's National Institute of Statistics and rendered as a live, explorable atlas.
      </p>
    </div>
    <div class="map-canvas-wrap">
      <img class="hero-photo" id="heroPhoto" src="data:image/jpeg;base64,{mediterranean_b64}" alt="Satellite view of the Mediterranean basin, from the Iberian peninsula and the Alps to Turkey and the Sahara" />
      <svg class="atlas-map" id="atlasSvg" viewBox="{FULL_VIEWBOX[0]} {FULL_VIEWBOX[1]} {FULL_VIEWBOX[2]} {FULL_VIEWBOX[3]}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <clipPath id="countryClip"><path d="{COUNTRY_PATH}"/></clipPath>
          <radialGradient id="seaGradient" cx="42%" cy="38%" r="75%">
            <stop offset="0%" stop-color="#0e3350"/>
            <stop offset="45%" stop-color="#0a2740"/>
            <stop offset="100%" stop-color="#061627"/>
          </radialGradient>
        </defs>
        <rect x="{FULL_VIEWBOX[0]}" y="{FULL_VIEWBOX[1]}" width="{FULL_VIEWBOX[2]}" height="{FULL_VIEWBOX[3]}" fill="url(#seaGradient)" opacity="0.93"/>
        <text class="sea-label" x="{W*0.62}" y="{H*0.28}">MEDITERRANEAN SEA</text>
        <path class="land" d="{OTHER_LAND_PATH}"/>
        <g id="flagLayer" clip-path="url(#countryClip)">
          <path d="{COUNTRY_PATH}" fill="#c8102e"/>
          <circle cx="{flag_cx}" cy="{flag_cy}" r="{flag_r}" fill="#fdfdfb"/>
          <circle cx="{flag_cx}" cy="{flag_cy}" r="{crescent_outer_r}" fill="#c8102e"/>
          <circle cx="{flag_cx + crescent_offset}" cy="{flag_cy}" r="{crescent_inner_r}" fill="#fdfdfb"/>
          <polygon points="{STAR_PTS}" fill="#c8102e"/>
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
    <div class="hero-scrim" id="heroScrim"></div>
    <div class="hero-scroll-hint" id="scrollHint"><span>Scroll to explore</span><span class="chevron"></span></div>
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
  Governorate boundaries: TUN_adm1 shapefile. Neighboring coastlines: Natural Earth (public domain, 110m).
  Mediterranean satellite composite: NASA Earth Observatory / Worldview imagery, public domain.
  National emblem: Wikimedia Commons, public domain.<br/>
  Each governorate panel shows one real, verified monument photo (Wikimedia Commons, freely licensed, credited
  in-panel) and a description condensed from that governorate's English Wikipedia article. Where a governorate
  has no single iconic built landmark, the closest real, well-documented site was used instead of inventing one.
</div>

<script>
const PAYLOAD = {json.dumps(PAYLOAD, ensure_ascii=False)};
const FULL_VB = {json.dumps(FULL_VIEWBOX)};
const TUNISIA_VB = {json.dumps(TUNISIA_VIEWBOX)};

const spacer = document.querySelector('.scroll-spacer');
const heroPhoto = document.getElementById('heroPhoto');
const heroText = document.getElementById('heroText');
const heroScrim = document.getElementById('heroScrim');
const scrollHint = document.getElementById('scrollHint');
const svg = document.getElementById('atlasSvg');
const flagLayer = document.getElementById('flagLayer');
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

function onScroll() {{
  const releaseScroll = spacer.offsetHeight - window.innerHeight;
  const p = Math.max(0, Math.min(1, window.scrollY / (releaseScroll * 0.92)));
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
  const vbH = expLerp(FULL_VB[3], TUNISIA_VB[3], zoomP);
  const cx = lerp(FULL_CX, TUNISIA_CX, zoomP);
  const cy = lerp(FULL_CY, TUNISIA_CY, zoomP);
  const vb = [cx - vbW/2, cy - vbH/2, vbW, vbH];
  svg.setAttribute('viewBox', vb.join(' '));

  // The satellite photo is the establishing shot ("this is the
  // Mediterranean, and here's Tunisia in it"). expLerp's zoom is already
  // ~30% done by p=0.16 (equal RATIO per scroll tick, front-loaded in
  // absolute terms) — fading the photo out that slowly left it half-
  // transparent right as the solid-red flag layer became prominent
  // underneath, alpha-blending into a muddy pink smear. Matching the
  // photo's dissolve pace to the zoom's own pace (fully gone by p=0.12,
  // vs. 0.25 before) keeps the two in the same rhythm instead of one
  // lagging visibly behind the other.
  heroPhoto.style.opacity = String(Math.max(0, 1 - p / 0.12));
  heroText.style.opacity = String(Math.max(0, 1 - p / 0.3));
  heroScrim.style.opacity = String(Math.max(0, 1 - p / 0.3));
  heroText.style.transform = `translateY(${{-p*40}}px)`;
  scrollHint.style.opacity = String(Math.max(0, 1 - p / 0.15));
  document.getElementById('locator').style.opacity = String(Math.max(0, 1 - p / 0.2));

  flagLayer.setAttribute('opacity', String(1 - revealP));
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

function colorFor(v, lo, hi) {{
  if (hi <= lo) return RAMP[Math.floor(RAMP.length/2)];
  const t = (v - lo) / (hi - lo);
  return RAMP[Math.max(0, Math.min(RAMP.length-1, Math.round(t * (RAMP.length-1))))];
}}

function paintMap() {{
  const theme = PAYLOAD.themes[currentTheme];
  const d = PAYLOAD.data[theme.slug];
  const values = Object.values(d.values);
  const lo = Math.min(...values), hi = Math.max(...values);
  document.getElementById('legendTitle').textContent = d.label + ' · ' + d.year;
  document.getElementById('legendLo').textContent = lo.toLocaleString();
  document.getElementById('legendHi').textContent = hi.toLocaleString();
  dataLayer.querySelectorAll('.region').forEach(function(el) {{
    const v = d.values[el.dataset.gov];
    el.setAttribute('fill', v !== undefined ? colorFor(v, lo, hi) : '#1a1f29');
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
