# Tunisia Socioeconomic Dashboard

An interactive dashboard over Tunisia's [National Institute of Statistics (INS)](https://www.ins.tn)
data — population, employment & living conditions, prices & economy, and
education & health, by governorate (and by delegation where available).

The INS publishes a data portal at `dataportal.ins.tn` with no documented
public API. This project reverse-engineers its internal XML query endpoints
into a typed Python client, builds a reproducible ETL pipeline on top of it,
and serves the result through a Streamlit app.

## Architecture

```
src/tn_dashboard/
├── ins_api/        # low-level client for dataportal.ins.tn + cached catalog
├── geo/            # governorate/delegation name matching (API/CSV <-> shapefile)
└── etl/            # indicator scoring, dataset build, DuckDB schema
scripts/run_etl.py  # end-to-end job: API -> data/tunisia.duckdb
app/streamlit_app.py  # reads ONLY data/tunisia.duckdb, no network calls
config/indicators.yaml  # human-curated indicator registry
tests/              # unit tests against fixed API-response fixtures (no live calls)
```

The ETL job and the dashboard are fully decoupled: `run_etl.py` is the only
thing that talks to the INS API and (re)builds `data/tunisia.duckdb`; the
Streamlit app only ever reads from that file. `data/raw/ins_catalog/*.json`
caches the INS source/indicator/region catalogs so the pipeline doesn't
depend on the live server being reachable to run its tests.

### How indicators were chosen

The INS's main source (`C_NSO`) has ~5,700 indicators. `etl/score_indicators.py`
prunes that down with a depth/keyword heuristic, then empirically scores
survivors on temporal span, recency, regional granularity actually achieved,
and completeness (`data/interim/indicator_scores.csv`). The ~48 indicators
actually shipped in `config/indicators.yaml` are a human-reviewed shortlist
from that ranking — see the file for the full list and units. A legacy
delegation-level 2015 poverty/school-dropout dataset (extracted from a 2020
INS PDF report) is merged in alongside the API data.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,app]"
```

## Running

```bash
# (Re)build the database by pulling every configured indicator from the live API
python scripts/run_etl.py

# Launch the dashboard (reads data/tunisia.duckdb, no network calls)
streamlit run app/streamlit_app.py
```

A pre-built `data/tunisia.duckdb` is committed, so `streamlit run` works
right after cloning without running the ETL job first.

## Docker

```bash
docker build -t tn-dashboard .
docker run -p 8501:8501 tn-dashboard                    # serve the app
docker run tn-dashboard python scripts/run_etl.py        # refresh the data instead
```

## Tests

```bash
pytest
ruff check .
```

Tests run against fixed XML fixtures captured from real API responses
(`tests/fixtures/`) — no network access required, and CI runs on every push.
A separate scheduled workflow (`.github/workflows/refresh-data.yml`) runs
the real ETL job against the live API and commits the refreshed database.

## Data sources

- [INS Data Portal](http://dataportal.ins.tn) — population, employment,
  prices, education, health and other socioeconomic indicators by region.
- INS 2020 report — 2015 poverty and school dropout rates by delegation
  (`data/raw/ins_tunisia_report_2020.pdf`, extracted in `notebooks/`).
- Administrative boundaries: `data/raw/TUN_adm1.shp` (governorate/delegation shapefile).
