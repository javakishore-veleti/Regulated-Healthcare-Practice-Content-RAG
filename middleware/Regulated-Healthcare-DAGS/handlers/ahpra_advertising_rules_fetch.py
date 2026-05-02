"""Fetcher for `dataset_type == 'regulator_guidelines'` in Project A.

Imported and called by `regulated_healthcare_dataset_ingest` when the dispatcher
sees a regulator-guidelines dataset. Lives outside the DAGs scan path via the
sibling `.airflowignore` (`^handlers/`).

Implementation is a thin wrapper over the shared `fetch_url_list` helper —
all dataset-type-specific config (the fallback URL list, the handler name)
lives here; the rest is reused.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

# Load the sibling helper by file path so this works regardless of how Airflow's
# task runner has set up sys.path inside the forked subprocess.
_helper_path = Path(__file__).parent / "_url_list_fetcher.py"
_spec = importlib.util.spec_from_file_location(
    "rhc_handlers._url_list_fetcher", _helper_path
)
assert _spec is not None and _spec.loader is not None
_url_list_fetcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_url_list_fetcher)


HANDLER_NAME = "ahpra_advertising_rules_fetch"

DEFAULT_REGULATOR_URLS_FALLBACK: list[str] = [
    # Stable smoke source used only when conf.urls is empty AND DataMgmt-Service
    # is unreachable AND the dataset has no curated URLs. Real curation belongs
    # in the dataset_source_urls admin table, not here.
    "https://en.wikipedia.org/wiki/Australian_Health_Practitioner_Regulation_Agency",
]


def fetch_ahpra_advertising_rules(resolved: dict[str, Any]) -> dict[str, Any]:
    """Fetch curated AHPRA / FTC / regulator-guideline URLs into the dataset's
    Latest_Ingest folder, save raw response bodies, and write the manifest."""
    return _url_list_fetcher.fetch_url_list(
        resolved,
        handler_name=HANDLER_NAME,
        fallback_urls=DEFAULT_REGULATOR_URLS_FALLBACK,
    )
