"""Pure data-shaping functions for the dashboard — no Streamlit, no I/O,
so these are unit-testable against a plain DataFrame. Kept separate from
streamlit_app.py's rendering code on purpose.
"""

from __future__ import annotations

import pandas as pd


def kpi_info(df: pd.DataFrame, slug: str) -> dict:
    """Latest value + period-over-period change for one indicator.

    Prefers the indicator's own national-level rows; if none exist (e.g. a
    delegation-only dataset like the 2015 poverty survey), falls back to
    the median across whatever regions it does have, with no change figure
    (there's nothing to compare against in a single-year dataset).
    """
    sub = df[df["slug"] == slug]
    national = sub[sub["region_level"] == "national"].sort_values("year")

    if not national.empty:
        last = national.iloc[-1]
        delta = None
        prev_year = None
        if len(national) > 1:
            prev = national.iloc[-2]
            delta = round(last["value"] - prev["value"], 3)
            prev_year = int(prev["year"])
        return {
            "value": round(float(last["value"]), 3),
            "year": int(last["year"]),
            "delta": delta,
            "prev_year": prev_year,
            "is_national": True,
        }

    latest_year = sub["year"].max()
    vals = sub[sub["year"] == latest_year]["value"]
    return {
        "value": round(float(vals.median()), 3),
        "year": int(latest_year),
        "delta": None,
        "prev_year": None,
        "is_national": False,
    }


def coverage_text(df: pd.DataFrame, slug: str) -> str:
    sub = df[df["slug"] == slug]
    levels = set(sub["region_level"].unique())
    if "delegation" in levels or "sector" in levels:
        n = sub[sub["region_level"].isin(["delegation", "sector"])]["region_name"].nunique()
        return f"{n} delegations"
    if "governorate" in levels:
        n = sub[sub["region_level"] == "governorate"]["region_name"].nunique()
        return f"{n} governorates"
    return "National only"


def governorate_values(df: pd.DataFrame, slug: str, year: int | None = None) -> dict[str, float]:
    """{governorate: value} for the given year (latest available if None),
    averaging finer-grained rows (delegation/sector) up to their governorate.
    """
    sub = df[(df["slug"] == slug) & df["governorate"].notna()]
    if sub.empty:
        return {}
    target_year = year if year is not None else sub["year"].max()
    sub = sub[sub["year"] == target_year]
    return sub.groupby("governorate")["value"].mean().round(3).to_dict()


def ranking_rows(df: pd.DataFrame, slug: str, year: int | None = None) -> list[tuple[str, float]]:
    values = governorate_values(df, slug, year)
    return sorted(values.items(), key=lambda kv: -kv[1])


def distribution(df: pd.DataFrame, slug: str) -> dict | None:
    """Lowest/median/highest across whatever finest-grained regions exist,
    for single-snapshot datasets with no time series to chart.
    """
    sub = df[df["slug"] == slug]
    if sub.empty:
        return None
    has_delegation = "delegation" in sub["region_level"].values
    finest = "delegation" if has_delegation else sub["region_level"].iloc[0]
    rows = sub[sub["region_level"] == finest][["region_name", "value"]].sort_values("value")
    if rows.empty:
        return None
    lo = rows.iloc[0]
    hi = rows.iloc[-1]
    return {
        "lowest": (lo["region_name"], round(float(lo["value"]), 3)),
        "median": round(float(rows["value"].median()), 3),
        "highest": (hi["region_name"], round(float(hi["value"]), 3)),
    }


def trend_series(df: pd.DataFrame, slug: str) -> dict:
    """Primary series (national, or governorate-average fallback) plus, if
    governorate-level data exists, the two most extreme governorates at the
    latest year as thin context series — the 'emphasis' chart pattern.
    """
    sub = df[df["slug"] == slug]
    national = sub[sub["region_level"] == "national"].sort_values("year")

    if not national.empty:
        primary = national[["year", "value"]].reset_index(drop=True)
        primary_label = "National"
    else:
        gov_rows = sub[sub["governorate"].notna()]
        primary = gov_rows.groupby("year", as_index=False)["value"].mean()
        primary_label = "National (governorate average)"

    context = []
    gov_rows = sub[sub["governorate"].notna()]
    if not gov_rows.empty:
        latest_year = gov_rows["year"].max()
        latest = gov_rows[gov_rows["year"] == latest_year].groupby("governorate")["value"].mean()
        if len(latest) >= 2:
            lo_gov, hi_gov = latest.idxmin(), latest.idxmax()
            for gov, tag in [(lo_gov, "lowest"), (hi_gov, "highest")]:
                one_gov = gov_rows[gov_rows["governorate"] == gov]
                series = one_gov.groupby("year", as_index=False)["value"].mean()
                if len(series) > 1:
                    context.append({"name": gov, "tag": tag, "series": series})

    return {"primary": primary, "primary_label": primary_label, "context": context}
