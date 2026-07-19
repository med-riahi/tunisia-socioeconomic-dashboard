import geopandas as gpd
import pandas as pd
import pytest

from tn_dashboard.config import CLEAN_DIR, RAW_DIR, TUNISIA_GOVERNORATES
from tn_dashboard.geo import names

SHAPEFILE = RAW_DIR / "TUN_adm1.shp"
POVERTY_CSV = CLEAN_DIR / "tunisia_poverty_2015_cleaned.csv"

pytestmark = pytest.mark.skipif(
    not SHAPEFILE.exists() or not POVERTY_CSV.exists(),
    reason="shapefile/poverty CSV not present in this checkout",
)

NON_DELEGATION_PLACEHOLDERS = {"Unknown", "Unknown1", "Lake Ichkeul"}


@pytest.fixture(scope="module")
def shapefile_gdf():
    return gpd.read_file(SHAPEFILE, encoding="ISO-8859-1")


def test_all_governorates_match(shapefile_gdf):
    matched = names.add_governorate_column(shapefile_gdf)

    assert set(matched["Governorate"].unique()) == set(TUNISIA_GOVERNORATES)
    assert matched["Governorate"].isna().sum() == 0


def test_all_real_delegations_match(shapefile_gdf):
    governed = names.add_governorate_column(shapefile_gdf)
    reference_names = pd.read_csv(POVERTY_CSV)["Delegation"].tolist()

    matched = names.add_delegation_column(governed, reference_names)
    real_rows = matched[~matched["NAME_2"].isin(NON_DELEGATION_PLACEHOLDERS)]

    assert real_rows["Delegation"].isna().sum() == 0
    assert len(real_rows) == 265


def test_match_delegation_names_skips_known_placeholders():
    mapping = names.match_delegation_names(
        ["Unknown", "Ariana City"], reference_names=["Ariana City"]
    )

    assert "Unknown" not in mapping
    assert mapping["Ariana City"] == "Ariana City"


def test_clean_governorate_name_handles_encoding_artifacts():
    assert names.clean_governorate_name("BA(c)ja") == "Beja"
    assert names.clean_governorate_name('GabA"s') == "Gabes"
    assert names.clean_governorate_name("not a governorate") is None
