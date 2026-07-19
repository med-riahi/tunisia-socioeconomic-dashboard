"""Fetch-once, cache-to-disk layer over the INS API client.

The full source list and the two big dimension trees (indicators, regions)
for the main C_NSO source rarely change and are expensive to re-fetch (the
indicator tree alone is a couple MB of XML). We cache them as JSON under
data/raw/ins_catalog/ so the rest of the pipeline — and CI — doesn't depend
on dataportal.ins.tn being reachable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict

from tn_dashboard import config
from tn_dashboard.ins_api.client import (
    DimensionNode,
    Source,
    get_dimension_elements,
    get_structure,
)

logger = logging.getLogger(__name__)

STRUCTURE_CACHE = config.CATALOG_DIR / "structure.json"
INDICATORS_CACHE = config.CATALOG_DIR / "indicators_c_nso.json"
REGIONS_CACHE = config.CATALOG_DIR / "regions_c_nso.json"


def _node_to_dict(node: DimensionNode) -> dict:
    return {
        "key": node.key,
        "name": node.name,
        "full_name": node.full_name,
        "unit": node.unit,
        "children": [_node_to_dict(c) for c in node.children],
    }


def _dict_to_node(d: dict) -> DimensionNode:
    return DimensionNode(
        key=d["key"],
        name=d["name"],
        full_name=d["full_name"],
        unit=d["unit"],
        children=[_dict_to_node(c) for c in d["children"]],
    )


def fetch_and_cache_structure(force: bool = False) -> list[Source]:
    if STRUCTURE_CACHE.exists() and not force:
        raw = json.loads(STRUCTURE_CACHE.read_text())
        return [Source(**s) for s in raw]

    logger.info("Fetching source structure from INS API...")
    sources = get_structure()
    payload = json.dumps([asdict(s) for s in sources], ensure_ascii=False, indent=2)
    STRUCTURE_CACHE.write_text(payload)
    return sources


def fetch_and_cache_indicator_tree(
    source_id: str = config.INS_MAIN_SOURCE_ID, force: bool = False
) -> list[DimensionNode]:
    if INDICATORS_CACHE.exists() and not force:
        raw = json.loads(INDICATORS_CACHE.read_text())
        return [_dict_to_node(n) for n in raw]

    logger.info("Fetching indicator dimension tree for %s from INS API...", source_id)
    nodes = get_dimension_elements(source_id, config.INS_INDICATOR_DIMENSION_ID)
    payload = json.dumps([_node_to_dict(n) for n in nodes], ensure_ascii=False, indent=2)
    INDICATORS_CACHE.write_text(payload)
    return nodes


def fetch_and_cache_region_tree(
    source_id: str = config.INS_MAIN_SOURCE_ID, force: bool = False
) -> list[DimensionNode]:
    if REGIONS_CACHE.exists() and not force:
        raw = json.loads(REGIONS_CACHE.read_text())
        return [_dict_to_node(n) for n in raw]

    logger.info("Fetching region dimension tree for %s from INS API...", source_id)
    nodes = get_dimension_elements(source_id, config.INS_REGION_DIMENSION_ID)
    payload = json.dumps([_node_to_dict(n) for n in nodes], ensure_ascii=False, indent=2)
    REGIONS_CACHE.write_text(payload)
    return nodes


# --------------------------------------------------------------------------
# Region key -> {name, level, governorate} lookup
# --------------------------------------------------------------------------

GOVERNORATE_PREFIXES = ("Gouvernorat de ", "Gouvernorat du ", "Gouvernorat d'")
DELEGATION_PREFIX = "Délégation de "
# "District de Tunis" is how the region tree represents Tunis governorate at
# the macro-region level (it has no "Gouvernorat de Tunis" sibling of its
# own elsewhere) — some indicators tag Tunis-governorate rows with this key
# directly, so it must classify as a governorate, not a macro-region.
DISTRICT_PREFIX = "District de "


def _strip_governorate_prefix(name: str) -> str:
    for prefix in GOVERNORATE_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):].strip()
    return name[len(DISTRICT_PREFIX):].strip()


def _classify(
    nodes: list[DimensionNode], depth: int, current_gov: str | None, registry: dict
) -> None:
    for node in nodes:
        name = node.name.strip()
        if depth == 0:
            level, gov = "national", None
        elif name.startswith(GOVERNORATE_PREFIXES) or name.startswith(DISTRICT_PREFIX):
            level, gov = "governorate", _strip_governorate_prefix(name)
        elif name.startswith(DELEGATION_PREFIX):
            level, gov = "delegation", current_gov
        elif depth == 1:
            level, gov = "macro_region", None
        else:
            level, gov = "sector", current_gov

        registry[node.key] = {"name": name, "level": level, "governorate": gov}
        next_gov = gov if level == "governorate" else current_gov
        _classify(node.children, depth + 1, next_gov, registry)


def build_region_lookup(region_tree: list[DimensionNode]) -> dict[str, dict]:
    """Map region KEY -> {name, level, governorate}.

    `level` is one of national/macro_region/governorate/delegation/sector.
    `governorate` is the cleaned governorate name a node falls under (None
    for national/macro-region nodes), used to join API data back onto the
    TUN_adm1 shapefile via tn_dashboard.geo.names.
    """
    registry: dict[str, dict] = {}
    _classify(region_tree, depth=0, current_gov=None, registry=registry)
    return registry


def load_region_lookup() -> dict[str, dict]:
    return build_region_lookup(fetch_and_cache_region_tree())


def refresh_all(force: bool = False) -> None:
    fetch_and_cache_structure(force=force)
    fetch_and_cache_indicator_tree(force=force)
    fetch_and_cache_region_tree(force=force)
