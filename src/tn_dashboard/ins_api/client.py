"""Thin client for the (undocumented) INS data portal API at dataportal.ins.tn.

The portal runs on Prognoz Platform. There's no official REST/JSON API and no
auth is required: you POST a small XML "QueryMessage" to one of a few
WebApi endpoints and get an XML response back. This was reverse-engineered
from the portal's own client-side JS (DPEngine.AP.Api._sendRequest), which
calls `{AppUrl}Get{MenuId}` — see tests/fixtures/*.xml for real captured
responses this client is validated against.
"""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from xml.sax.saxutils import escape, quoteattr

import requests

from tn_dashboard.config import INS_BASE_URL

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 3


class InsApiError(RuntimeError):
    """Raised when the INS data portal can't be reached or returns unparseable XML."""


def _post(action: str, query_xml: str, timeout: int = DEFAULT_TIMEOUT) -> ET.Element:
    url = f"{INS_BASE_URL}{action}"
    headers = {
        "Content-Type": "text/xml; charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (compatible; tn-dashboard-etl/0.1)",
    }
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url, data=query_xml.encode("utf-8"), headers=headers, timeout=timeout
            )
            resp.raise_for_status()
            return ET.fromstring(resp.content)
        except (requests.RequestException, ET.ParseError) as exc:
            last_exc = exc
            logger.warning(
                "INS API call to %s failed (attempt %d/%d): %s", action, attempt, MAX_RETRIES, exc
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    raise InsApiError(f"{action} failed after {MAX_RETRIES} attempts") from last_exc


def _attr(value: str) -> str:
    return quoteattr(value)


# --------------------------------------------------------------------------
# GetStructure — list of data sources
# --------------------------------------------------------------------------


@dataclass
class SourceDimension:
    id: str
    name: str
    dimension_type: str


@dataclass
class Source:
    id: str
    name: str
    description: str
    start_year: int | None
    finish_year: int | None
    dimensions: list[SourceDimension] = field(default_factory=list)


def parse_structure(root: ET.Element) -> list[Source]:
    sources = []
    for src_el in root.findall(".//Source"):
        period_el = src_el.find("Period")
        start_year = finish_year = None
        if period_el is not None:
            start_el, finish_el = period_el.find("StartYear"), period_el.find("FinishYear")
            start_year = int(start_el.text) if start_el is not None and start_el.text else None
            finish_year = int(finish_el.text) if finish_el is not None and finish_el.text else None

        dims = []
        for dim_el in src_el.findall("./Dimensions/Dimension"):
            dims.append(
                SourceDimension(
                    id=dim_el.get("Id", ""),
                    name=dim_el.get("Name", ""),
                    dimension_type=dim_el.get("DimensionType", ""),
                )
            )

        desc_el = src_el.find("Description")
        sources.append(
            Source(
                id=src_el.get("Id", ""),
                name=src_el.get("Name", ""),
                description=(desc_el.text or "") if desc_el is not None else "",
                start_year=start_year,
                finish_year=finish_year,
                dimensions=dims,
            )
        )
    return sources


def get_structure() -> list[Source]:
    root = _post("GetStructure", "<QueryMessage></QueryMessage>")
    return parse_structure(root)


# --------------------------------------------------------------------------
# GetDimensionElements — the indicator / region trees
# --------------------------------------------------------------------------


@dataclass
class DimensionNode:
    key: str
    name: str
    full_name: str
    unit: str
    children: list[DimensionNode] = field(default_factory=list)

    def is_leaf(self) -> bool:
        return not self.children

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def leaves(self):
        for node in self.walk():
            if node.is_leaf():
                yield node


def _parse_element_node(el: ET.Element) -> DimensionNode:
    return DimensionNode(
        key=el.get("KEY", ""),
        name=el.get("NAME", ""),
        full_name=el.get("FULLNAME", el.get("NAME", "")),
        unit=el.get("UNIT", ""),
        children=[_parse_element_node(child) for child in el.findall("Element")],
    )


def parse_dimension_elements(root: ET.Element) -> list[DimensionNode]:
    elements_el = root.find("Elements")
    if elements_el is None:
        return []
    return [_parse_element_node(el) for el in elements_el.findall("Element")]


def get_dimension_elements(
    source_id: str, dimension_id: str, with_data: bool = True
) -> list[DimensionNode]:
    query = (
        f"<QueryMessage SourceId={_attr(source_id)}>"
        f"<DataWhere><DimensionId WithData={_attr(str(with_data).lower())}>"
        f"{escape(dimension_id)}</DimensionId></DataWhere></QueryMessage>"
    )
    root = _post("GetDimensionElements", query, timeout=45)
    return parse_dimension_elements(root)


# --------------------------------------------------------------------------
# GetData — actual indicator values
# --------------------------------------------------------------------------


@dataclass
class DataPoint:
    year: int
    indicator_key: str
    region_key: str
    units: str
    value: float | None


def _build_data_query(
    source_id: str,
    indicator_dimension_id: str,
    indicator_keys: list[str],
    period_from: str,
    period_to: str,
    frequency: str,
    region_dimension_id: str | None = None,
    region_keys: list[str] | None = None,
) -> str:
    indicator_elements = "".join(f"<Element>{escape(k)}</Element>" for k in indicator_keys)
    where = (
        f"<Dimension Id={_attr(indicator_dimension_id)}>{indicator_elements}</Dimension>"
    )
    if region_dimension_id and region_keys:
        region_elements = "".join(f"<Element>{escape(k)}</Element>" for k in region_keys)
        where += f"<Dimension Id={_attr(region_dimension_id)}>{region_elements}</Dimension>"

    return (
        f"<QueryMessage SourceId={_attr(source_id)}>"
        f"<Period From={_attr(period_from)} To={_attr(period_to)} Frequency={_attr(frequency)}/>"
        f"<DataWhere>{where}</DataWhere>"
        f"</QueryMessage>"
    )


def parse_data_response(
    root: ET.Element, indicator_dimension_id: str, region_dimension_id: str
) -> list[DataPoint]:
    state = root.get("State", "")
    if state != "Success":
        logger.warning("GetData returned state=%s", state)
        return []

    points = []
    for set_el in root.findall("Set"):
        period = set_el.get("Period", "")
        year_part = period.split(":")[-1] if period else None
        try:
            year = int(year_part)
        except (TypeError, ValueError):
            continue

        text = (set_el.text or "").strip()
        value = float(text) if text else None

        points.append(
            DataPoint(
                year=year,
                indicator_key=set_el.get(indicator_dimension_id, ""),
                region_key=set_el.get(region_dimension_id, ""),
                units=set_el.get("UNITS", ""),
                value=value,
            )
        )
    return points


def get_data(
    source_id: str,
    indicator_keys: list[str],
    period_from: str,
    period_to: str,
    frequency: str = "Y",
    region_keys: list[str] | None = None,
    indicator_dimension_id: str = "RDS_DICT_INDICATORS_NSO",
    region_dimension_id: str = "RDS_DICT_REGIONS_NSO",
) -> list[DataPoint]:
    """Fetch data points for one or more indicator keys.

    Omitting `region_keys` (the default) is deliberate: the API then returns
    every region that indicator actually has data for, which is how we
    discover real regional granularity instead of assuming a fixed level.
    """
    query = _build_data_query(
        source_id=source_id,
        indicator_dimension_id=indicator_dimension_id,
        indicator_keys=indicator_keys,
        period_from=period_from,
        period_to=period_to,
        frequency=frequency,
        region_dimension_id=region_dimension_id if region_keys else None,
        region_keys=region_keys,
    )
    root = _post("GetData", query)
    return parse_data_response(root, indicator_dimension_id, region_dimension_id)
