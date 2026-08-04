#!/usr/bin/env python
"""End-to-end ETL job: pulls every configured indicator from the live INS
API, merges in the legacy 2015 poverty/dropout dataset, and (re)builds
data/tunisia.duckdb. This is what the scheduled GitHub Action runs, and
what `docker run <image> python scripts/run_etl.py` runs.

Pass --only slug1,slug2 to fetch just those indicators (e.g. ones just added
to config/indicators.yaml) and backfill everything else from the existing
database untouched — much faster than a full sweep when the portal is slow,
and the default no-argument behavior (fetch everything) is unchanged.
"""

import argparse

from tn_dashboard.etl import build_dataset, db


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only", default=None,
        help="Comma-separated slugs to fetch from the API; everything else is "
        "backfilled from the existing database instead of re-fetched.",
    )
    args = parser.parse_args()
    only_slugs = set(args.only.split(",")) if args.only else None

    df = build_dataset.build(only_slugs=only_slugs)

    con = db.connect()
    try:
        db.replace_indicators(con, df)
    finally:
        con.close()

    print(f"Loaded {len(df)} rows into {db.config.DUCKDB_PATH}")


if __name__ == "__main__":
    main()
