"""Tunisia socioeconomic dashboard. Reads only from data/tunisia.duckdb —
all ETL/network logic lives in tn_dashboard.etl and runs separately
(scripts/run_etl.py). This file has no INS API calls in it.
"""

from __future__ import annotations

import folium
import geopandas as gpd
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium

from tn_dashboard import config
from tn_dashboard.etl import db
from tn_dashboard.geo import names

THEME_GROUP_LABELS = {
    "population": "Population & Demographics",
    "employment_living_conditions": "Employment & Living Conditions",
    "prices_economy": "Prices & Economy",
    "education_health": "Education & Health",
}

# The only dataset with reliable delegation-level name matching (validated
# in tests/test_geo_names.py — 265/265 real delegations match). Every other
# indicator, even where the API itself has delegation/sector-level data, is
# aggregated up to governorate for the map since the API's French delegation
# names don't reliably match the shapefile without per-indicator alias work.
DELEGATION_MAP_SLUGS = {
    "poverty_rate_2015",
    "primary_dropout_rate_2015",
    "secondary_dropout_rate_2015",
    "total_dropout_rate_2015",
}

st.set_page_config(page_title="Tunisia Socioeconomic Dashboard", layout="wide")


@st.cache_data
def load_data() -> pd.DataFrame:
    con = db.connect()
    try:
        return db.load_indicators(con)
    finally:
        con.close()


@st.cache_data
def load_governorate_shapefile() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(config.RAW_DIR / "TUN_adm1.shp", encoding="ISO-8859-1")
    gdf = names.add_governorate_column(gdf)
    return gdf.dissolve(by="Governorate", as_index=False)


@st.cache_data
def load_delegation_shapefile(reference_names: tuple[str, ...]) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(config.RAW_DIR / "TUN_adm1.shp", encoding="ISO-8859-1")
    return names.add_delegation_column(gdf, list(reference_names))


def indicator_options(df: pd.DataFrame, theme_group: str) -> pd.DataFrame:
    subset = df[df["theme_group"] == theme_group]
    return subset[["slug", "name", "unit", "theme"]].drop_duplicates().sort_values("name")


def governorate_agg(df: pd.DataFrame, slug: str, year: int) -> pd.DataFrame:
    subset = df[(df["slug"] == slug) & (df["year"] == year) & df["governorate"].notna()]
    return subset.groupby("governorate", as_index=False)["value"].mean()


def timeseries(df: pd.DataFrame, slug: str) -> tuple[pd.DataFrame, str]:
    subset = df[df["slug"] == slug]
    national = subset[subset["region_level"] == "national"]
    if not national.empty:
        return national.groupby("year", as_index=False)["value"].mean(), "national"
    fallback = subset[subset["governorate"].notna()]
    return fallback.groupby("year", as_index=False)["value"].mean(), "governorate_average"


def render_map(df: pd.DataFrame, slug: str, year: int, unit: str) -> None:
    if slug in DELEGATION_MAP_SLUGS:
        subset = df[(df["slug"] == slug) & (df["year"] == year)]
        ref_names = tuple(sorted(subset["region_name"].unique()))
        gdf = load_delegation_shapefile(ref_names)
        merged = gdf.merge(subset, left_on="Delegation", right_on="region_name", how="left")
        key_on, columns, tooltip_fields, tooltip_aliases = (
            "feature.properties.Delegation",
            ["Delegation", "value"],
            ["Delegation", "value"],
            ["Delegation:", f"Value ({unit}):"],
        )
        st.caption("Delegation-level view.")
    else:
        agg = governorate_agg(df, slug, year)
        gdf = load_governorate_shapefile()
        merged = gdf.merge(agg, left_on="Governorate", right_on="governorate", how="left")
        key_on, columns, tooltip_fields, tooltip_aliases = (
            "feature.properties.Governorate",
            ["Governorate", "value"],
            ["Governorate", "value"],
            ["Governorate:", f"Value ({unit}):"],
        )
        st.caption(
            "Governorate-level view (averaged across finer-grained regions where applicable)."
        )

    if merged["value"].notna().sum() == 0:
        st.info("No regional data available for this indicator/year.")
        return

    minx, miny, maxx, maxy = merged.total_bounds
    center = ((miny + maxy) / 2, (minx + maxx) / 2)
    # folium's own fit_bounds()/zoom_start are unreliable inside
    # streamlit-folium's iframe (the size Leaflet sees at init time doesn't
    # match the final rendered size) — st_folium's own zoom/center kwargs
    # are the component's documented, reliable way to control the view.
    m = folium.Map(tiles="cartodbpositron")
    folium.Choropleth(
        geo_data=merged,
        data=merged,
        columns=columns,
        key_on=key_on,
        fill_color="YlOrRd",
        fill_opacity=0.75,
        line_opacity=0.3,
        legend_name=f"{unit}",
        nan_fill_color="lightgrey",
    ).add_to(m)
    folium.GeoJson(
        merged,
        tooltip=folium.GeoJsonTooltip(fields=tooltip_fields, aliases=tooltip_aliases),
        style_function=lambda x: {"fillOpacity": 0, "color": "black", "weight": 0.5},
    ).add_to(m)
    st_folium(m, use_container_width=True, height=520, center=center, zoom=6, returned_objects=[])


def main() -> None:
    st.title("Tunisia Socioeconomic Dashboard")
    st.caption(
        "Data: Institut National de la Statistique (INS) data portal "
        "+ 2020 INS report (2015 poverty survey)"
    )

    df = load_data()

    with st.sidebar:
        st.header("Filters")
        group_label = st.selectbox("Theme", list(THEME_GROUP_LABELS.values()))
        theme_group = next(k for k, v in THEME_GROUP_LABELS.items() if v == group_label)

        options = indicator_options(df, theme_group)
        indicator_label = st.selectbox("Indicator", options["name"].tolist())
        row = options[options["name"] == indicator_label].iloc[0]
        slug, unit = row["slug"], row["unit"]

        years = sorted(df[df["slug"] == slug]["year"].unique())
        year = st.select_slider("Year", options=years, value=years[-1])

    st.subheader(indicator_label)
    st.caption(f"Unit: {unit}")

    col_map, col_charts = st.columns([3, 2])

    with col_map:
        render_map(df, slug, year, unit)

    with col_charts:
        ts, ts_kind = timeseries(df, slug)
        ts_label = "National" if ts_kind == "national" else "National (governorate average)"
        fig_ts = px.line(ts, x="year", y="value", title=f"{ts_label} trend", markers=True)
        st.plotly_chart(fig_ts, use_container_width=True)

        agg = governorate_agg(df, slug, year)
        if not agg.empty:
            agg_sorted = agg.sort_values("value", ascending=False)
            fig_bar = px.bar(
                agg_sorted, x="value", y="governorate", orientation="h",
                title=f"By governorate ({year})",
            )
            fig_bar.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig_bar, use_container_width=True)


if __name__ == "__main__":
    main()
