import duckdb
import pandas as pd

from tn_dashboard.etl import db


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "slug": "birth_rate",
                "theme_group": "population",
                "theme": "Population",
                "name": "Natalité",
                "unit": "Pour 1000 habitants",
                "source": "ins_api",
                "region_key": "0",
                "region_name": "Tunisie",
                "region_level": "national",
                "governorate": None,
                "year": 2020,
                "value": 17.0,
            },
            {
                "slug": "poverty_rate_2015",
                "theme_group": "employment_living_conditions",
                "theme": "living_conditions_2015_pdf",
                "name": "Taux de pauvreté",
                "unit": "Pourcentage",
                "source": "pdf_2015",
                "region_key": None,
                "region_name": "La Medina",
                "region_level": "delegation",
                "governorate": "Tunis",
                "year": 2015,
                "value": 6.6,
            },
        ]
    )


def test_replace_indicators_creates_expected_schema_and_rows():
    con = duckdb.connect(":memory:")

    db.replace_indicators(con, _sample_df())
    result = db.load_indicators(con)

    assert len(result) == 2
    assert set(result.columns) == set(db.COLUMNS)
    assert set(result["slug"]) == {"birth_rate", "poverty_rate_2015"}


def test_replace_indicators_is_a_full_refresh_not_an_upsert():
    con = duckdb.connect(":memory:")

    db.replace_indicators(con, _sample_df())
    db.replace_indicators(con, _sample_df().head(1))
    result = db.load_indicators(con)

    assert len(result) == 1
    assert result.iloc[0]["slug"] == "birth_rate"
