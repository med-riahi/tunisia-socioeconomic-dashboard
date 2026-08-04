"""Phase 3: pull every indicator in config/indicators.yaml from the live API,
tag each row with its real regional granularity, fold in the legacy
PDF-derived poverty/dropout dataset, and produce one tidy long-format table.

Usage: python -m tn_dashboard.etl.build_dataset
"""

from __future__ import annotations

import logging
import time

import pandas as pd
import yaml

from tn_dashboard import config
from tn_dashboard.etl import db
from tn_dashboard.ins_api import catalog
from tn_dashboard.ins_api.client import InsApiError, get_data

logger = logging.getLogger(__name__)

REQUEST_DELAY_SECONDS = 0.15
PERIOD_FROM, PERIOD_TO = "1970", "2030"

LEGACY_POVERTY_CSV = config.CLEAN_DIR / "tunisia_poverty_2015_cleaned.csv"
LEGACY_POVERTY_YEAR = 2015
LEGACY_POVERTY_METRICS = {
    "poverty_rate_2015": ("Poverty%", "Taux de pauvreté (2015, rapport INS)", "Pourcentage"),
    "primary_dropout_rate_2015": (
        "PrimDrop%", "Taux d'abandon scolaire - cycle primaire (2015, rapport INS)", "Pourcentage"
    ),
    "secondary_dropout_rate_2015": (
        "SecDrop%", "Taux d'abandon scolaire - cycle secondaire (2015, rapport INS)", "Pourcentage"
    ),
    "total_dropout_rate_2015": (
        "TotalDrop%", "Taux d'abandon scolaire - total (2015, rapport INS)", "Pourcentage"
    ),
}


def load_indicator_config() -> list[dict]:
    with open(config.INDICATORS_CONFIG_PATH) as f:
        return yaml.safe_load(f)


def fetch_api_indicators(
    region_lookup: dict[str, dict], only_slugs: set[str] | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """Pulls every indicator in config/indicators.yaml from the live API, or
    just ``only_slugs`` when given — useful when adding a handful of new
    indicators to an already-built database, since a full 62-indicator sweep
    against this portal can take well over an hour if it's having a slow day
    (every request re-hits every indicator, including ones that haven't
    changed), whereas the new subset alone takes a couple of minutes."""
    entries = load_indicator_config()
    if only_slugs is not None:
        entries = [e for e in entries if e["slug"] in only_slugs]
    rows = []

    failed_slugs = []
    for i, entry in enumerate(entries, start=1):
        try:
            points = get_data(
                source_id=entry["source_id"],
                indicator_keys=[entry["indicator_key"]],
                period_from=PERIOD_FROM,
                period_to=PERIOD_TO,
            )
        except InsApiError as exc:
            # The live portal is occasionally flaky on a single indicator
            # (read timeouts) even after the client's own retries — one bad
            # indicator shouldn't discard everything else already fetched in
            # this run. Re-running the ETL later picks up anything skipped.
            logger.warning("skipping %s after repeated failures: %s", entry["slug"], exc)
            failed_slugs.append(entry["slug"])
            continue
        for p in points:
            if p.value is None:
                continue
            region_info = region_lookup.get(p.region_key, {})
            rows.append(
                {
                    "slug": entry["slug"],
                    "theme_group": entry["theme_group"],
                    "theme": entry["theme"],
                    "name": entry["name"],
                    "unit": entry["unit"],
                    "source": "ins_api",
                    "region_key": p.region_key,
                    "region_name": region_info.get("name", p.region_key),
                    "region_level": region_info.get("level", "national"),
                    "governorate": region_info.get("governorate"),
                    "year": p.year,
                    "value": p.value,
                }
            )
        if i % 10 == 0:
            logger.info("  ...%d/%d indicators fetched", i, len(entries))
        time.sleep(REQUEST_DELAY_SECONDS)

    logger.info("Fetched %d data points across %d indicators", len(rows), len(entries))
    if failed_slugs:
        logger.warning(
            "%d indicator(s) skipped this run, re-run the ETL to retry: %s",
            len(failed_slugs), ", ".join(failed_slugs),
        )
    return pd.DataFrame(rows), failed_slugs


def load_legacy_poverty_dataset() -> pd.DataFrame:
    if not LEGACY_POVERTY_CSV.exists():
        logger.warning("Legacy poverty CSV not found at %s, skipping", LEGACY_POVERTY_CSV)
        return pd.DataFrame()

    df = pd.read_csv(LEGACY_POVERTY_CSV)
    rows = []
    for _, record in df.iterrows():
        for slug, (column, name, unit) in LEGACY_POVERTY_METRICS.items():
            rows.append(
                {
                    "slug": slug,
                    "theme_group": "employment_living_conditions",
                    "theme": "living_conditions_2015_pdf",
                    "name": name,
                    "unit": unit,
                    "source": "pdf_2015",
                    "region_key": None,
                    "region_name": record["Delegation"],
                    "region_level": "delegation",
                    "governorate": record["Governorate"],
                    "year": LEGACY_POVERTY_YEAR,
                    "value": float(record[column]),
                }
            )
    logger.info("Loaded %d rows from the legacy 2015 poverty/dropout dataset", len(rows))
    return pd.DataFrame(rows)


def build(only_slugs: set[str] | None = None) -> pd.DataFrame:
    """Builds the full tidy dataset. If any indicator fails to fetch this
    run (the live portal is flaky — read timeouts on an otherwise-healthy
    indicator are common), its rows are backfilled from whatever is already
    in data/tunisia.duckdb rather than silently regressing that indicator to
    empty. The full-refresh write in db.replace_indicators() means a bad run
    would otherwise permanently lose an indicator that fetched fine before.

    Pass ``only_slugs`` to fetch just those from the live API (e.g. a
    handful of newly-added indicators) and backfill every other configured
    indicator from the existing database untouched — a full 62-indicator
    sweep can take well over an hour if the portal is having a slow day,
    when all you actually need is the couple you just added.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    region_lookup = catalog.load_region_lookup()

    api_df, failed_slugs = fetch_api_indicators(region_lookup, only_slugs=only_slugs)
    legacy_df = load_legacy_poverty_dataset()

    slugs_to_backfill = set(failed_slugs)
    if only_slugs is not None:
        all_slugs = {e["slug"] for e in load_indicator_config()}
        slugs_to_backfill |= all_slugs - set(only_slugs)

    if slugs_to_backfill and config.DUCKDB_PATH.exists():
        con = db.connect()
        try:
            existing = db.load_indicators(con)
        finally:
            con.close()
        backfill = existing[existing["slug"].isin(slugs_to_backfill)]
        if not backfill.empty:
            logger.warning(
                "backfilling %d row(s) for %d indicator(s) from the existing db (not re-fetched)",
                len(backfill), backfill["slug"].nunique(),
            )
            api_df = pd.concat([api_df, backfill], ignore_index=True)

    combined = pd.concat([api_df, legacy_df], ignore_index=True)
    combined["region_key"] = combined["region_key"].astype("string")
    combined["year"] = combined["year"].astype(int)
    combined["value"] = combined["value"].astype(float)
    return combined


if __name__ == "__main__":
    df = build()
    out_path = config.CLEAN_DIR / "ins_indicators.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df)} rows to {out_path}")
