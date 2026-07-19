"""Phase 2: prune the ~5,700-indicator C_NSO tree down to realistic candidates,
then empirically score each one against the live API so a human can pick the
best ~8-15 per theme group instead of either hand-picking blind or dumping
everything.

Usage: python -m tn_dashboard.etl.score_indicators
"""

from __future__ import annotations

import csv
import logging
import re
import time

from tn_dashboard import config
from tn_dashboard.ins_api import catalog
from tn_dashboard.ins_api.client import DimensionNode, get_data

logger = logging.getLogger(__name__)

# Which top-level C_NSO themes feed each theme group the user chose.
THEME_GROUPS: dict[str, list[str]] = {
    "population": ["Population"],
    "employment_living_conditions": ["Emploi", "Ménages et conditions de vie", "Salaires"],
    "prices_economy": ["Prix", "Budget", "Monnaie et banques"],
    "education_health": ["Education", "Santé"],
}

# Leaves deeper than this (relative to the theme root) tend to be
# hyper-specific cross-tabs (e.g. births by month by mother's age by
# delegation) rather than headline indicators, so they're dropped.
MAX_LEAF_DEPTH = 3

# Leaf names that are themselves just a breakdown value, not a real
# indicator (e.g. a bare sex or month split at the bottom of the tree).
NAME_DENYLIST = {
    "masculin", "féminin", "feminin", "homme", "femme",
    "janvier", "février", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "août", "aout", "septembre", "octobre", "novembre", "décembre", "decembre",
    "communal", "non communal",
}
AGE_BAND_RE = re.compile(r"^\d{1,3}([+]|-\d{1,3})?$")

CANDIDATES_PER_GROUP = 50
REQUEST_DELAY_SECONDS = 0.15
PERIOD_FROM, PERIOD_TO = "1970", "2030"

REGION_LEVEL_RANK = {
    "national": 0, "macro_region": 1, "governorate": 2, "delegation": 3, "sector": 4
}

SCORES_CSV = config.INTERIM_DIR / "indicator_scores.csv"


def _is_denied(name: str) -> bool:
    n = name.strip().lower()
    return n in NAME_DENYLIST or bool(AGE_BAND_RE.match(n))


def _collect_candidates(theme_node: DimensionNode, theme_name: str) -> list[dict]:
    candidates = []

    def walk(node: DimensionNode, depth: int, path: list[str]):
        current_path = [*path, node.name]
        if node.is_leaf():
            if depth <= MAX_LEAF_DEPTH and not any(_is_denied(p) for p in current_path):
                candidates.append(
                    {
                        "theme": theme_name,
                        "path": " > ".join(current_path),
                        "indicator_key": node.key,
                        "name": node.name,
                        "full_name": node.full_name,
                        "unit": node.unit,
                        "depth": depth,
                    }
                )
            return
        for child in node.children:
            walk(child, depth + 1, current_path)

    walk(theme_node, depth=0, path=[])
    return candidates


def prune_candidates(indicator_tree: list[DimensionNode]) -> dict[str, list[dict]]:
    by_theme_name = {node.name: node for node in indicator_tree}
    grouped: dict[str, list[dict]] = {}

    for group, theme_names in THEME_GROUPS.items():
        candidates = []
        for theme_name in theme_names:
            theme_node = by_theme_name.get(theme_name)
            if theme_node is None:
                logger.warning("Theme %r not found in indicator tree, skipping", theme_name)
                continue
            candidates.extend(_collect_candidates(theme_node, theme_name))

        # Prefer shallower (more headline-level) indicators when trimming to the cap.
        candidates.sort(key=lambda c: c["depth"])
        if len(candidates) > CANDIDATES_PER_GROUP:
            logger.info(
                "%s: %d candidates after pruning, capping to %d",
                group, len(candidates), CANDIDATES_PER_GROUP,
            )
            candidates = candidates[:CANDIDATES_PER_GROUP]
        grouped[group] = candidates

    return grouped


def _normalize(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def score_candidate(candidate: dict, region_lookup: dict[str, dict]) -> dict:
    points = get_data(
        source_id=config.INS_MAIN_SOURCE_ID,
        indicator_keys=[candidate["indicator_key"]],
        period_from=PERIOD_FROM,
        period_to=PERIOD_TO,
    )

    non_null = [p for p in points if p.value is not None]
    years = {p.year for p in non_null}
    regions = {p.region_key for p in non_null}
    levels = {region_lookup.get(r, {}).get("level", "national") for r in regions}
    max_level_rank = max((REGION_LEVEL_RANK.get(lv, 0) for lv in levels), default=0)
    max_level_name = next(
        (lv for lv, r in REGION_LEVEL_RANK.items() if r == max_level_rank), "national"
    )

    n_years = len(years)
    first_year = min(years) if years else None
    last_year = max(years) if years else None
    completeness = len(non_null) / len(points) if points else 0.0

    span_score = _normalize(n_years, 0, 40)
    recency_score = _normalize(last_year or 0, 1995, 2026)
    granularity_score = max_level_rank / max(REGION_LEVEL_RANK.values())
    composite = (
        0.35 * span_score + 0.25 * recency_score + 0.25 * granularity_score + 0.15 * completeness
    )

    return {
        **candidate,
        "n_years": n_years,
        "first_year": first_year,
        "last_year": last_year,
        "n_regions": len(regions),
        "max_region_level": max_level_name,
        "completeness": round(completeness, 3),
        "score": round(composite, 4),
    }


def run(limit_per_group: int | None = None) -> list[dict]:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    indicator_tree = catalog.fetch_and_cache_indicator_tree()
    region_lookup = catalog.load_region_lookup()

    grouped_candidates = prune_candidates(indicator_tree)
    total = sum(len(v) for v in grouped_candidates.values())
    logger.info("Scoring %d candidates across %d theme groups...", total, len(grouped_candidates))

    all_results = []
    done = 0
    for group, candidates in grouped_candidates.items():
        if limit_per_group:
            candidates = candidates[:limit_per_group]
        for candidate in candidates:
            try:
                result = score_candidate(candidate, region_lookup)
                result["theme_group"] = group
                all_results.append(result)
            except Exception:
                logger.exception(
                    "Failed to score %s (%s)", candidate["name"], candidate["indicator_key"]
                )
            done += 1
            if done % 20 == 0:
                logger.info("  ...%d/%d scored", done, total)
            time.sleep(REQUEST_DELAY_SECONDS)

    before = len(all_results)
    all_results = [r for r in all_results if r["n_years"] > 0]
    if before != len(all_results):
        logger.info("Dropped %d candidates with no data at all", before - len(all_results))

    all_results.sort(key=lambda r: (r["theme_group"], -r["score"]))

    fieldnames = [
        "theme_group", "theme", "path", "indicator_key", "name", "full_name", "unit",
        "n_years", "first_year", "last_year", "n_regions", "max_region_level",
        "completeness", "score",
    ]
    with open(SCORES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_results)

    logger.info("Wrote %d scored indicators to %s", len(all_results), SCORES_CSV)
    return all_results


if __name__ == "__main__":
    run()
