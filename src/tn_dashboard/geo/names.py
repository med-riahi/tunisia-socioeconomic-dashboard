"""Match Tunisia governorate/delegation names between the TUN_adm1 shapefile
and whatever dataset we're joining onto it. Extracted from the exploratory
logic in notebooks/02_cleaning.ipynb and notebooks/03_visualization.ipynb
(unchanged behavior, just reusable functions instead of copy-pasted cells).
"""

from __future__ import annotations

import unidecode
from rapidfuzz import fuzz, process

from tn_dashboard.config import TUNISIA_GOVERNORATES

# The shapefile's NAME_1 values, once transliterated with unidecode, are
# mangled in inconsistent ways (encoding artifacts, alternate spellings).
# This maps each of those to the canonical name in TUNISIA_GOVERNORATES.
_GOVERNORATE_ALIASES = {
    "Ariana": "Ariana",
    "BA(c)ja": "Beja",
    "Ben Arous (Tunis Sud)": "Ben Arous",
    "Bizerte": "Bizerte",
    'GabA"s': "Gabes",
    "Gafsa": "Gafsa",
    "Jendouba": "Jendouba",
    "Kairouan": "Kairouan",
    "KassA(c)rine": "Kasserine",
    "Kebili": "Kebili",
    "Le Kef": "Kef",
    "Mahdia": "Mahdia",
    "Manubah": "Manouba",
    "MA(c)denine": "Medenine",
    "Monastir": "Monastir",
    "Nabeul": "Nabeul",
    "Sfax": "Sfax",
    "Sidi Bou Zid": "Sidi Bouzid",
    "Siliana": "Siliana",
    "Sousse": "Sousse",
    "Tataouine": "Tataouine",
    "Tozeur": "Tozeur",
    "Tunis": "Tunis",
    "Zaghouan": "Zaghouan",
}

# French administrative-name suffixes/words the shapefile uses that the
# reference delegation lists (extracted from PDF reports) spell in English.
_FRENCH_TO_ENGLISH = {
    "Sud": "South",
    "Ville": "City",
    "Ouest": "West",
    "Est": "East",
    "Nord": "North",
    "Centre": "Center",
    "Nouvelle": "New",
    "Superieur": "Superior",
}

# Rows in the shapefile's NAME_2 that aren't real delegations.
_NON_DELEGATION_NAMES = {"Unknown", "Unknown1", "Lake Ichkeul"}

# The original notebook exploration always took rapidfuzz's top match with
# no minimum-score cutoff (so even a mediocre match like 'Bou Argoub' ->
# 'Ben Arous' gets accepted) — kept as the default here so behavior is
# unchanged; pass a higher min_score to reject low-confidence matches.
MIN_DELEGATION_MATCH_SCORE = 0

_DELEGATION_TREE_PREFIXES = ("Délégation de ", "Délégation d'", "Délégation du ")


def strip_delegation_prefix(name: str) -> str:
    """Strip the INS API region tree's 'Délégation de ' prefix, e.g. for
    matching its delegation names (French) against the shapefile's NAME_2.
    """
    for prefix in _DELEGATION_TREE_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):].strip()
    return name


def clean_governorate_name(raw_name: str) -> str | None:
    """Map a shapefile NAME_1 value to a canonical governorate name, or None."""
    transliterated = unidecode.unidecode(raw_name)
    return _GOVERNORATE_ALIASES.get(transliterated)


def add_governorate_column(gdf, source_column: str = "NAME_1", target_column: str = "Governorate"):
    """Return a copy of `gdf` with a cleaned, canonical governorate column."""
    out = gdf.copy()
    out[target_column] = out[source_column].apply(clean_governorate_name)
    unmatched = out[out[target_column].isna()][source_column].unique().tolist()
    if unmatched:
        raise ValueError(f"Unmatched governorate names in {source_column}: {unmatched}")
    missing = set(TUNISIA_GOVERNORATES) - set(out[target_column].unique())
    if missing:
        raise ValueError(f"Governorates missing from shapefile after matching: {sorted(missing)}")
    return out


def _translate_french_words(name: str) -> str:
    return " ".join(_FRENCH_TO_ENGLISH.get(word, word) for word in name.split())


def match_delegation_names(
    shapefile_names: list[str],
    reference_names: list[str],
    min_score: float = MIN_DELEGATION_MATCH_SCORE,
) -> dict[str, str | None]:
    """Fuzzy-match shapefile NAME_2 values to a reference list of delegation
    names (e.g. from a cleaned CSV). Returns {shapefile_name: best_match or None}.

    Translates common French words to English first (the shapefile is in
    French, most reference datasets in this project use English delegation
    names), then uses rapidfuzz token-sort matching, same as the original
    notebook exploration — kept here so any new delegation-level dataset
    joins the shapefile the same way.
    """
    candidates = [n for n in shapefile_names if n not in _NON_DELEGATION_NAMES]
    translated = {n: _translate_french_words(n) for n in candidates}

    mapping: dict[str, str | None] = {}
    for original, translated_name in translated.items():
        best = process.extractOne(translated_name, reference_names, scorer=fuzz.token_sort_ratio)
        mapping[original] = best[0] if best and best[1] >= min_score else None
    return mapping


def add_delegation_column(
    gdf,
    reference_names: list[str],
    source_column: str = "NAME_2",
    target_column: str = "Delegation",
):
    """Return a copy of `gdf` with a fuzzy-matched delegation column."""
    mapping = match_delegation_names(gdf[source_column].tolist(), reference_names)
    out = gdf.copy()
    out[target_column] = out[source_column].map(mapping)
    return out
