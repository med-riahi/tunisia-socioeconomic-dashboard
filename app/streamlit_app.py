"""Tunisia socioeconomic dashboard. Reads only from data/tunisia.duckdb —
all ETL/network logic lives in tn_dashboard.etl and runs separately
(scripts/run_etl.py). This file has no INS API calls in it.

Visual design: a custom SVG choropleth (map_component.py) instead of
folium/Leaflet — crisp at any size, no basemap tiles, and it sidesteps the
iframe-sizing bugs that made folium unreliable for a narrow, tall country.
Colors/fonts/card styling live in theme.py; the pure data-shaping logic
(what to show, not how to draw it) lives in data_helpers.py and is unit
tested independently of Streamlit.
"""

from __future__ import annotations

import geopandas as gpd
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from atlas import build_atlas_html
from data_helpers import (
    coverage_text,
    distribution,
    governorate_values,
    kpi_info,
    ranking_rows,
    trend_series,
)
from map_component import render_choropleth_html
from theme import (
    CARD_CLOSE,
    COLORS,
    card_open,
    distribution_html,
    kpi_row_html,
    load_css,
    masthead_html,
    ranking_html,
)
from tn_dashboard import config
from tn_dashboard.etl import db
from tn_dashboard.geo import names
from tn_dashboard.geo.svg import region_svg_paths

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

st.set_page_config(
    page_title="Tunisia Socioeconomic Dashboard", layout="wide", initial_sidebar_state="collapsed"
)
st.markdown(load_css(), unsafe_allow_html=True)


@st.cache_data
def load_data() -> pd.DataFrame:
    con = db.connect()
    try:
        return db.load_indicators(con)
    finally:
        con.close()


@st.cache_data
def load_governorate_paths() -> dict[str, str]:
    gdf = gpd.read_file(config.RAW_DIR / "TUN_adm1.shp", encoding="ISO-8859-1")
    gdf = names.add_governorate_column(gdf)
    gdf = gdf.dissolve(by="Governorate", as_index=False)
    return region_svg_paths(gdf, "Governorate")


@st.cache_data
def load_delegation_paths(reference_names: tuple[str, ...]) -> dict[str, str]:
    gdf = gpd.read_file(config.RAW_DIR / "TUN_adm1.shp", encoding="ISO-8859-1")
    gdf = names.add_delegation_column(gdf, list(reference_names))
    gdf = gdf.dropna(subset=["Delegation"])
    gdf = gdf.dissolve(by="Delegation", as_index=False)
    return region_svg_paths(gdf, "Delegation", simplify_tolerance=0.004)


def indicator_options(df: pd.DataFrame, theme_group: str) -> pd.DataFrame:
    subset = df[df["theme_group"] == theme_group]
    return subset[["slug", "name", "unit"]].drop_duplicates().sort_values("name")


def format_value(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 100:
        return f"{value:,.1f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def render_kpis(df: pd.DataFrame, slug: str, unit: str) -> None:
    info = kpi_info(df, slug)
    cov = coverage_text(df, slug)

    if info["delta"] is not None:
        arrow = "▲" if info["delta"] > 0 else ("▼" if info["delta"] < 0 else "—")
        delta_text = f"{arrow} {format_value(abs(info['delta']))}"
    elif info["is_national"]:
        delta_text = "— flat"
    else:
        delta_text = "single survey"

    st.markdown(
        kpi_row_html(format_value(info["value"]), unit, info["year"], delta_text, cov),
        unsafe_allow_html=True,
    )


def render_trend(df: pd.DataFrame, slug: str) -> None:
    t = trend_series(df, slug)
    fig = go.Figure()
    for c in t["context"]:
        label = f"{c['name']} ({c['tag']})"
        fig.add_trace(
            go.Scatter(
                x=c["series"]["year"], y=c["series"]["value"], mode="lines", name=label,
                line=dict(color=COLORS["ink_3"], width=1.4), opacity=0.55,
                hovertemplate="%{y}<extra>" + label + "</extra>",
            )
        )
    tick_font = dict(family="Menlo, monospace", size=10)
    fig.add_trace(
        go.Scatter(
            x=t["primary"]["year"], y=t["primary"]["value"], mode="lines+markers",
            name=t["primary_label"], marker=dict(size=5),
            line=dict(color=COLORS["accent"], width=2.75),
            hovertemplate="%{y}<extra>" + t["primary_label"] + "</extra>",
        )
    )
    fig.update_layout(
        height=260,
        margin=dict(l=4, r=4, t=4, b=4),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="-apple-system, sans-serif", color=COLORS["ink_2"], size=12),
        xaxis=dict(showgrid=False, showline=False, tickfont=tick_font),
        yaxis=dict(showgrid=True, gridcolor=COLORS["border"], zeroline=False, tickfont=tick_font),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=11)),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_ranking_card(
    df: pd.DataFrame, slug: str, year: int | None, val_fmt: str = "{:.1f}"
) -> None:
    rows = ranking_rows(df, slug, year)
    head = card_open("By governorate, ranked", f"n = {len(rows)}")
    st.markdown(head + ranking_html(rows, val_fmt) + CARD_CLOSE, unsafe_allow_html=True)


def render_governorate_panel(df: pd.DataFrame, name: str, slug: str, unit: str) -> None:
    years = sorted(df[df["slug"] == slug]["year"].unique())
    year = st.select_slider("Year", options=years, value=years[-1])

    col_map, col_right = st.columns([3, 2])
    with col_map:
        values = governorate_values(df, slug, year)
        paths = load_governorate_paths()
        st.markdown(card_open(f"{name} by governorate", f"{year} · {unit}"), unsafe_allow_html=True)
        components.html(render_choropleth_html(paths, values, unit), height=520, scrolling=False)
        if values:
            lo, hi = min(values.values()), max(values.values())
            note = (
                f'<div class="tn-note">{format_value(lo)} &ndash; '
                f"{format_value(hi)} {unit}</div>"
            )
        else:
            note = '<div class="tn-note">No regional data for this year.</div>'
        st.markdown(note, unsafe_allow_html=True)
        st.markdown(CARD_CLOSE, unsafe_allow_html=True)

    with col_right:
        st.markdown(card_open("Trend"), unsafe_allow_html=True)
        render_trend(df, slug)
        st.markdown(CARD_CLOSE, unsafe_allow_html=True)
        render_ranking_card(df, slug, year)


def render_delegation_panel(df: pd.DataFrame, name: str, slug: str, unit: str) -> None:
    sub = df[df["slug"] == slug]
    year = int(sub["year"].iloc[0])
    ref_names = tuple(sorted(sub["region_name"].dropna().unique()))
    values = sub.groupby("region_name")["value"].mean().to_dict()
    paths = load_delegation_paths(ref_names)

    col_map, col_right = st.columns([3, 2])
    with col_map:
        st.markdown(card_open(f"{name} by delegation", f"{year} · {unit}"), unsafe_allow_html=True)
        components.html(render_choropleth_html(paths, values, unit), height=520, scrolling=False)
        n_matched = len(set(values) & set(paths))
        st.markdown(
            f'<div class="tn-note">{n_matched} / {len(values)} delegations matched to map '
            f"boundaries by name &mdash; the rest render unfilled.</div>",
            unsafe_allow_html=True,
        )
        st.markdown(CARD_CLOSE, unsafe_allow_html=True)

    with col_right:
        d = distribution(df, slug)
        st.markdown(card_open("Distribution", "single survey year"), unsafe_allow_html=True)
        st.markdown(
            distribution_html(d["lowest"], d["median"], d["highest"]), unsafe_allow_html=True
        )
        st.markdown(
            '<div class="tn-note">Extracted from a 2020 INS PDF report, not the live API '
            "&mdash; a one-off survey, so there's no time series to chart.</div>",
            unsafe_allow_html=True,
        )
        st.markdown(CARD_CLOSE, unsafe_allow_html=True)
        render_ranking_card(df, slug, year)


def render_national_panel(df: pd.DataFrame, name: str, slug: str, unit: str) -> None:
    st.markdown(card_open(f"{name} — national trend"), unsafe_allow_html=True)
    render_trend(df, slug)
    st.markdown(
        '<div class="tn-note">Published at national level only &mdash; the source data has '
        "no regional breakdown for this indicator.</div>",
        unsafe_allow_html=True,
    )
    st.markdown(CARD_CLOSE, unsafe_allow_html=True)


def render_atlas() -> None:
    # Strips Streamlit's default block-container padding/max-width and hides
    # its header so the cinematic scroll experience runs edge-to-edge inside
    # the iframe instead of sitting in a padded box within a padded page.
    # The iframe's declared height (below) only affects Streamlit's own
    # layout math; forcing it to 100vh here is what actually makes the
    # opening view fill the whole screen instead of leaving Streamlit's page
    # background visible beneath a fixed-height box.
    st.markdown(
        """
        <style>
        .block-container { padding: 0 !important; max-width: 100% !important; }
        header[data-testid="stHeader"] { background: transparent; }
        iframe { display: block; height: 100vh !important; }
        html, body { overflow: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    df = load_data()
    components.html(build_atlas_html(df), height=1000, scrolling=True)


def render_classic() -> None:
    df = load_data()

    st.markdown(
        masthead_html(
            "Tunisia Socioeconomic Dashboard",
            "Population, employment, prices, and health &mdash; by governorate, "
            "pulled live from the INS data portal.",
        ),
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Filters")
        group_label = st.selectbox("Theme", list(THEME_GROUP_LABELS.values()))
        theme_group = next(k for k, v in THEME_GROUP_LABELS.items() if v == group_label)

        options = indicator_options(df, theme_group)
        indicator_label = st.selectbox("Indicator", options["name"].tolist())
        row = options[options["name"] == indicator_label].iloc[0]
        slug, unit = row["slug"], row["unit"]

    render_kpis(df, slug, unit)

    levels = set(df[df["slug"] == slug]["region_level"].unique())
    if slug in DELEGATION_MAP_SLUGS:
        render_delegation_panel(df, indicator_label, slug, unit)
    elif "governorate" in levels:
        render_governorate_panel(df, indicator_label, slug, unit)
    else:
        render_national_panel(df, indicator_label, slug, unit)


def main() -> None:
    with st.sidebar:
        view = st.radio("View", ["Data Atlas", "Classic Explorer"], index=0)
        st.caption(
            "Data Atlas is the cinematic scroll map (population/economy/health "
            "by governorate). Classic Explorer drills into all 48 indicators "
            "with trend charts and rankings."
        )

    if view == "Data Atlas":
        render_atlas()
    else:
        render_classic()


if __name__ == "__main__":
    main()
