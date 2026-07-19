#!/usr/bin/env python
"""End-to-end ETL job: pulls every configured indicator from the live INS
API, merges in the legacy 2015 poverty/dropout dataset, and (re)builds
data/tunisia.duckdb. This is what the scheduled GitHub Action runs, and
what `docker run <image> python scripts/run_etl.py` runs.
"""

from tn_dashboard.etl import build_dataset, db


def main() -> None:
    df = build_dataset.build()

    con = db.connect()
    try:
        db.replace_indicators(con, df)
    finally:
        con.close()

    print(f"Loaded {len(df)} rows into {db.config.DUCKDB_PATH}")


if __name__ == "__main__":
    main()
