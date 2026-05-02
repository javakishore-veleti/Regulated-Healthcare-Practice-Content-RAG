"""Fetcher for `dataset_type == 'pubmed'` (NCBI / HuggingFace `ncbi/pubmed`).

Pulls the curated documentation / index URLs for the PubMed corpus. The actual
NCBI PubMed dataset (~25 GB raw, ~6 GB MSK-filtered) is downloaded by a
separate, opt-in slice using the HuggingFace `datasets` library or NCBI's
E-utilities — this handler just lays down the dataset-card + landing pages so
the corpus has a written description ingested under `Latest_Ingest/raw/`.
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


HANDLER_NAME = "ncbi_pubmed_fetch"

DEFAULT_PUBMED_URLS_FALLBACK: list[str] = [
    "https://huggingface.co/datasets/ncbi/pubmed",
    "https://pubmed.ncbi.nlm.nih.gov/about/",
]


def fetch_ncbi_pubmed(resolved: dict[str, Any]) -> dict[str, Any]:
    return _url_list_fetcher.fetch_url_list(
        resolved,
        handler_name=HANDLER_NAME,
        fallback_urls=DEFAULT_PUBMED_URLS_FALLBACK,
    )
