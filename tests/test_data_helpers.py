import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from data_helpers import (  # noqa: E402
    coverage_text,
    distribution,
    governorate_values,
    kpi_info,
    ranking_rows,
    trend_series,
)


def _row(slug, year, value, region_level, region_name, governorate=None):
    return {
        "slug": slug, "theme_group": "population", "theme": "Population", "name": slug,
        "unit": "u", "source": "ins_api", "region_key": None,
        "region_name": region_name, "region_level": region_level,
        "governorate": governorate, "year": year, "value": value,
    }


def test_kpi_info_uses_national_rows_and_computes_delta():
    df = pd.DataFrame([
        _row("x", 2020, 10.0, "national", "Tunisie"),
        _row("x", 2021, 12.0, "national", "Tunisie"),
    ])
    info = kpi_info(df, "x")
    assert info == {
        "value": 12.0, "year": 2021, "delta": 2.0, "prev_year": 2020, "is_national": True,
    }


def test_kpi_info_falls_back_to_median_when_no_national_rows():
    df = pd.DataFrame([
        _row("x", 2015, 10.0, "delegation", "A", governorate="Tunis"),
        _row("x", 2015, 30.0, "delegation", "B", governorate="Sfax"),
    ])
    info = kpi_info(df, "x")
    assert info["value"] == 20.0
    assert info["delta"] is None
    assert info["is_national"] is False


def test_coverage_text_prefers_finer_granularity_label():
    df = pd.DataFrame([
        _row("x", 2015, 1.0, "delegation", "A", governorate="Tunis"),
        _row("x", 2015, 2.0, "governorate", "Tunis", governorate="Tunis"),
    ])
    assert coverage_text(df, "x") == "1 delegations"


def test_coverage_text_national_only():
    df = pd.DataFrame([_row("x", 2020, 1.0, "national", "Tunisie")])
    assert coverage_text(df, "x") == "National only"


def test_governorate_values_averages_finer_rows_per_governorate():
    df = pd.DataFrame([
        _row("x", 2015, 10.0, "delegation", "A", governorate="Tunis"),
        _row("x", 2015, 20.0, "delegation", "B", governorate="Tunis"),
        _row("x", 2015, 5.0, "delegation", "C", governorate="Sfax"),
    ])
    values = governorate_values(df, "x")
    assert values == {"Tunis": 15.0, "Sfax": 5.0}


def test_ranking_rows_sorted_descending():
    df = pd.DataFrame([
        _row("x", 2015, 5.0, "governorate", "Sfax", governorate="Sfax"),
        _row("x", 2015, 15.0, "governorate", "Tunis", governorate="Tunis"),
    ])
    assert ranking_rows(df, "x") == [("Tunis", 15.0), ("Sfax", 5.0)]


def test_distribution_picks_lowest_median_highest():
    df = pd.DataFrame([
        _row("x", 2015, 1.0, "delegation", "Low", governorate="Tunis"),
        _row("x", 2015, 5.0, "delegation", "Mid", governorate="Tunis"),
        _row("x", 2015, 9.0, "delegation", "High", governorate="Tunis"),
    ])
    d = distribution(df, "x")
    assert d["lowest"] == ("Low", 1.0)
    assert d["median"] == 5.0
    assert d["highest"] == ("High", 9.0)


def test_trend_series_adds_lowest_and_highest_governorate_context():
    df = pd.DataFrame([
        _row("x", 2020, 10.0, "national", "Tunisie"),
        _row("x", 2021, 11.0, "national", "Tunisie"),
        _row("x", 2020, 5.0, "governorate", "Kef", governorate="Kef"),
        _row("x", 2021, 6.0, "governorate", "Kef", governorate="Kef"),
        _row("x", 2020, 20.0, "governorate", "Tunis", governorate="Tunis"),
        _row("x", 2021, 22.0, "governorate", "Tunis", governorate="Tunis"),
    ])
    result = trend_series(df, "x")
    assert result["primary_label"] == "National"
    assert len(result["primary"]) == 2
    tags = {c["name"]: c["tag"] for c in result["context"]}
    assert tags == {"Kef": "lowest", "Tunis": "highest"}


def test_trend_series_falls_back_to_governorate_average_when_no_national():
    df = pd.DataFrame([
        _row("x", 2015, 10.0, "delegation", "A", governorate="Tunis"),
        _row("x", 2016, 12.0, "delegation", "A", governorate="Tunis"),
    ])
    result = trend_series(df, "x")
    assert result["primary_label"] == "National (governorate average)"
    assert list(result["primary"]["value"]) == [10.0, 12.0]
