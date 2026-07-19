"""DuckDB schema and load functions. The Streamlit app only ever reads from
this database — all ETL/network logic lives upstream in build_dataset.py.
"""

from __future__ import annotations

import duckdb
import pandas as pd

from tn_dashboard import config

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS indicators (
    slug TEXT NOT NULL,
    theme_group TEXT NOT NULL,
    theme TEXT NOT NULL,
    name TEXT NOT NULL,
    unit TEXT,
    source TEXT NOT NULL,
    region_key TEXT,
    region_name TEXT NOT NULL,
    region_level TEXT NOT NULL,
    governorate TEXT,
    year INTEGER NOT NULL,
    value DOUBLE
);
"""

COLUMNS = [
    "slug", "theme_group", "theme", "name", "unit", "source",
    "region_key", "region_name", "region_level", "governorate", "year", "value",
]


def connect(db_path=config.DUCKDB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path))


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA_SQL)


def replace_indicators(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> None:
    """Full-refresh load: the ETL job always rebuilds the whole table from
    scratch rather than upserting, since the source data is small and this
    avoids any stale-row bookkeeping.
    """
    init_schema(con)
    con.execute("DELETE FROM indicators")
    con.register("df_view", df)
    columns = ", ".join(COLUMNS)
    con.execute(f"INSERT INTO indicators ({columns}) SELECT {columns} FROM df_view")
    con.unregister("df_view")


def load_indicators(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute("SELECT * FROM indicators").fetchdf()
