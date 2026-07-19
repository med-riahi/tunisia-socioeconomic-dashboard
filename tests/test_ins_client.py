from pathlib import Path

import pytest
import responses

from tn_dashboard.config import INS_BASE_URL
from tn_dashboard.ins_api import client

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


@responses.activate
def test_get_structure_parses_sources():
    responses.add(
        responses.POST, f"{INS_BASE_URL}GetStructure", body=_fixture("structure_response.xml")
    )

    sources = client.get_structure()

    assert [s.id for s in sources] == ["C_NSO", "OBJ4325069"]
    nso = sources[0]
    assert nso.name == "Socio-économique"
    assert nso.start_year == 1970
    assert nso.finish_year == 2050
    expected_dims = {"UNITS", "RDS_DICT_INDICATORS_NSO", "RDS_DICT_REGIONS_NSO"}
    assert {d.id for d in nso.dimensions} == expected_dims


@responses.activate
def test_get_dimension_elements_builds_tree():
    responses.add(
        responses.POST,
        f"{INS_BASE_URL}GetDimensionElements",
        body=_fixture("indicators_response.xml"),
    )

    nodes = client.get_dimension_elements("C_NSO", "RDS_DICT_INDICATORS_NSO")

    assert [n.name for n in nodes] == ["Population", "Agriculture"]
    population = nodes[0]
    leaves = list(population.leaves())
    assert {leaf.name for leaf in leaves} == {"Natalité", "Mortalité"}
    assert leaves[0].unit == "Pour 1000 Habitants"


@responses.activate
def test_get_data_parses_points_and_handles_missing_values():
    responses.add(responses.POST, f"{INS_BASE_URL}GetData", body=_fixture("data_response.xml"))

    points = client.get_data(
        source_id="C_NSO",
        indicator_keys=["27529859"],
        period_from="2010",
        period_to="2019",
    )

    assert len(points) == 6
    national_2012 = next(p for p in points if p.region_key == "0" and p.year == 2012)
    assert national_2012.value == pytest.approx(20.2)

    missing = next(p for p in points if p.year == 2019)
    assert missing.value is None

    # no region filter was requested -> both region "0" (national) and "2" came back,
    # which is how granularity gets discovered rather than assumed.
    assert {p.region_key for p in points} == {"0", "2"}


@responses.activate
def test_get_data_returns_empty_on_failure_state():
    responses.add(responses.POST, f"{INS_BASE_URL}GetData", body='<Series State="Error"/>')

    points = client.get_data(
        source_id="C_NSO", indicator_keys=["999"], period_from="2010", period_to="2019"
    )

    assert points == []
