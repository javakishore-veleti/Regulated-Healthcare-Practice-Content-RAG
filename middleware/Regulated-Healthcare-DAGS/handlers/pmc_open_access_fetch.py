"""Fetcher for `dataset_type == 'pmc'` (PubMed Central Open Access Subset).

Pulls the curated documentation / OAI URLs for the PMC OA Subset. The actual
~50 GB OA full-text corpus (sampled to ~5 GB for Project A) is downloaded by a
separate, opt-in slice — this handler ingests the catalog / about pages so the
RAG stack has the corpus's licensing + structure documented locally.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_helper_path = Path(__file__).parent / "_url_list_fetcher.py"
_spec = importlib.util.spec_from_file_location(
    "rhc_handlers._url_list_fetcher", _helper_path
)
assert _spec is not None and _spec.loader is not None
_url_list_fetcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_url_list_fetcher)


HANDLER_NAME = "pmc_open_access_fetch"

DEFAULT_PMC_URLS_FALLBACK: list[str] = [
    "https://pmc.ncbi.nlm.nih.gov/about/",
    "https://www.ncbi.nlm.nih.gov/pmc/tools/openftlist/",
]


def fetch_pmc_open_access(resolved: dict[str, Any]) -> dict[str, Any]:
    return _url_list_fetcher.fetch_url_list(
        resolved,
        handler_name=HANDLER_NAME,
        fallback_urls=DEFAULT_PMC_URLS_FALLBACK,
    )
