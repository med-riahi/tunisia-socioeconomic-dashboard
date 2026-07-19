from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
CLEAN_DIR = DATA_DIR / "clean"
CATALOG_DIR = RAW_DIR / "ins_catalog"

CONFIG_DIR = REPO_ROOT / "config"
INDICATORS_CONFIG_PATH = CONFIG_DIR / "indicators.yaml"

DUCKDB_PATH = DATA_DIR / "tunisia.duckdb"

INS_BASE_URL = "http://dataportal.ins.tn/WebApi/"
INS_MAIN_SOURCE_ID = "C_NSO"
INS_INDICATOR_DIMENSION_ID = "RDS_DICT_INDICATORS_NSO"
INS_REGION_DIMENSION_ID = "RDS_DICT_REGIONS_NSO"

TUNISIA_GOVERNORATES = [
    "Ariana", "Beja", "Ben Arous", "Bizerte", "Gabes", "Gafsa", "Jendouba",
    "Kairouan", "Kasserine", "Kebili", "Kef", "Mahdia", "Manouba", "Medenine",
    "Monastir", "Nabeul", "Sfax", "Sidi Bouzid", "Siliana", "Sousse",
    "Tataouine", "Tozeur", "Tunis", "Zaghouan",
]

for _dir in (RAW_DIR, INTERIM_DIR, CLEAN_DIR, CATALOG_DIR, CONFIG_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
