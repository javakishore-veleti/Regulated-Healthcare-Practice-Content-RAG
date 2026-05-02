"""Fetcher for `dataset_type == 'pmc_fulltext'` — PMC Open Access full-text
articles via NCBI E-utilities efetch.

Distinct from `pmc_open_access_fetch.py`, which only pulls the PMC catalog /
about pages. This handler pulls actual article XML the chunker can index.

Each curated source URL is expected to be an NCBI E-utilities efetch call:
    https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi
        ?db=pmc&id=<NUMERIC_PMCID>&rettype=full&retmode=xml

NCBI rate-limit context:
* 3 requests/second is the unauthenticated limit. We default to 0.4s spacing
  (~2.5 QPS) to stay safely below it.
* With an `NCBI_API_KEY`, the limit lifts to 10 req/sec; this handler doesn't
  inject the key for now, but operators can append `&api_key=...` to each
  curated URL or extend this handler to do it. Either way the env-var-driven
  spacing in the shared fetcher (RHC_FETCHER_INTER_REQUEST_SECS) is the
  single knob to pull during a heavy crawl.

Real curation belongs in the DataMgmt admin portal (dataset_source_urls). The
fallback below is one stable NCBI page that documents the efetch API itself —
enough to prove the wiring on a fresh stack without seeding a guess at a real
PMCID.
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


HANDLER_NAME = "pmc_full_text_efetch"

# NCBI-polite spacing. The shared fetcher's default is 0.4s; we re-state it
# here as a documentation hook so tuning this handler specifically doesn't
# require touching the shared default.
PMC_INTER_REQUEST_SECS = 0.4

DEFAULT_PMC_EFETCH_FALLBACK: list[str] = [
    # NCBI's E-utilities documentation landing — public, stable, returns HTML.
    # This is a smoke-only fallback; real ingest URLs come from DataMgmt curation.
    # Operators add curated efetch URLs through the admin portal once a target
    # PMCID list is settled.
    "https://www.ncbi.nlm.nih.gov/books/NBK25500/",
]


def fetch_pmc_full_text_efetch(resolved: dict[str, Any]) -> dict[str, Any]:
    """Pull PMC OA full-text article XML via NCBI E-utilities efetch."""
    return _url_list_fetcher.fetch_url_list(
        resolved,
        handler_name=HANDLER_NAME,
        fallback_urls=DEFAULT_PMC_EFETCH_FALLBACK,
        file_extension="xml",
        inter_request_secs=PMC_INTER_REQUEST_SECS,
    )
