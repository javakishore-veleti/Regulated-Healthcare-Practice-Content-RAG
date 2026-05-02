"""Fetcher for `dataset_type == 'pubmed_abstracts'` — PubMed abstracts via
NCBI E-utilities esearch + efetch.

Distinct from the existing `ncbi_pubmed_fetch.py` handler, which only pulls
the PubMed about / catalog pages. This handler runs the canonical NCBI
search→fetch flow:

    1. esearch — given a curated search URL like
         https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi
            ?db=pubmed&term=physiotherapy+review&retmax=5
       parse the returned XML for `<IdList><Id>PMID</Id>...</IdList>`.
    2. efetch — for each PMID, GET
         https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi
            ?db=pubmed&id=<PMID>&rettype=abstract&retmode=xml
       and save the XML response to raw/.

Operators curate the search URLs through the DataMgmt admin portal
(dataset_source_urls). The fallback below is one stable physiotherapy-review
search so a fresh stack proves the path without committing to an opinionated
PMID list. PMIDs per query are capped at MAX_PMIDS_PER_QUERY so a single
curated query can't blow up an ingest run; tune via env (RHC_PUBMED_MAX_PMIDS).

Rate-limit: NCBI E-utilities allows 3 QPS unauthenticated; we space
both esearch and efetch calls at PUBMED_INTER_REQUEST_SECS (0.4s ~ 2.5 QPS).
With NCBI_API_KEY set the limit is 10 QPS — that path is opt-in via a future
slice; for now this handler stays under the unauthenticated cap.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)


# Load the shared retry / URL-resolution helpers. Same `importlib.util.spec_from_file_location`
# pattern the rest of the handlers use — works regardless of how Airflow's task
# runner sets up sys.path inside the forked subprocess.
_helper_path = Path(__file__).parent / "_url_list_fetcher.py"
_spec = importlib.util.spec_from_file_location(
    "rhc_handlers._url_list_fetcher", _helper_path
)
assert _spec is not None and _spec.loader is not None
_url_list_fetcher = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_url_list_fetcher)

_get_with_retry = _url_list_fetcher._get_with_retry
_resolve_urls = _url_list_fetcher._resolve_urls
DEFAULT_USER_AGENT = _url_list_fetcher.DEFAULT_USER_AGENT


HANDLER_NAME = "pubmed_abstracts_efetch"

EFETCH_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_INTER_REQUEST_SECS = 0.4
MAX_PMIDS_PER_QUERY = int(os.environ.get("RHC_PUBMED_MAX_PMIDS", "10"))

DEFAULT_PUBMED_SEARCH_FALLBACK: list[str] = [
    # Stable, low-volume search — proves the wiring on a fresh stack without
    # committing to an opinionated PMID curation. Real production setups
    # curate searches through the admin portal.
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    "?db=pubmed&term=physiotherapy+review&retmax=5",
]


def fetch_pubmed_abstracts(resolved: dict[str, Any]) -> dict[str, Any]:
    """Run esearch on each curated search URL, then efetch each returned PMID."""
    target = Path(resolved["destination_path"])
    target.mkdir(parents=True, exist_ok=True)

    raw_dir = target / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    search_urls, url_source = _resolve_urls(resolved, DEFAULT_PUBMED_SEARCH_FALLBACK)
    LOGGER.info(
        "[%s] %d search url(s) for dataset=%s (source=%s, max_pmids_per_query=%d)",
        HANDLER_NAME,
        len(search_urls),
        resolved["dataset_name"],
        url_source,
        MAX_PMIDS_PER_QUERY,
    )

    session = requests.Session()
    session.headers.update({"User-Agent": DEFAULT_USER_AGENT})

    fetched: list[dict[str, Any]] = []

    for s_idx, search_url in enumerate(search_urls):
        if s_idx > 0:
            time.sleep(PUBMED_INTER_REQUEST_SECS)

        # Step 1: esearch
        esearch_outcome: dict[str, Any] = {
            "phase": "esearch",
            "search_index": s_idx,
            "url": search_url,
        }
        try:
            LOGGER.info("[%s] esearch %s", HANDLER_NAME, search_url)
            resp = _get_with_retry(session, search_url, handler_name=HANDLER_NAME)
            pmids = _parse_pmids(resp.text)[:MAX_PMIDS_PER_QUERY]
            esearch_outcome.update(
                status="success",
                http_status=resp.status_code,
                pmid_count=len(pmids),
            )
        except (requests.RequestException, ET.ParseError) as exc:
            LOGGER.warning("[%s] esearch failed for %s: %r", HANDLER_NAME, search_url, exc)
            esearch_outcome.update(status="failure", error=repr(exc))
            fetched.append(esearch_outcome)
            continue
        fetched.append(esearch_outcome)

        if not pmids:
            LOGGER.info("[%s] esearch returned 0 PMIDs for %s", HANDLER_NAME, search_url)
            continue

        # Step 2: efetch each PMID
        for pmid_idx, pmid in enumerate(pmids):
            time.sleep(PUBMED_INTER_REQUEST_SECS)
            efetch_url = (
                f"{EFETCH_BASE}?db=pubmed&id={pmid}&rettype=abstract&retmode=xml"
            )
            outcome: dict[str, Any] = {
                "phase": "efetch",
                "search_index": s_idx,
                "search_url": search_url,
                "pmid": pmid,
                "pmid_index": pmid_idx,
                "url": efetch_url,
            }
            try:
                LOGGER.info("[%s] efetch PMID=%s", HANDLER_NAME, pmid)
                resp = _get_with_retry(session, efetch_url, handler_name=HANDLER_NAME)
                fname = f"{s_idx:03d}_{pmid_idx:03d}_pmid_{pmid}.xml"
                outpath = raw_dir / fname
                outpath.write_bytes(resp.content)
                outcome.update(
                    status="success",
                    http_status=resp.status_code,
                    bytes=len(resp.content),
                    content_type=resp.headers.get("content-type"),
                    saved_to=str(outpath.relative_to(target)),
                )
            except requests.RequestException as exc:
                LOGGER.warning(
                    "[%s] efetch failed for PMID=%s: %r", HANDLER_NAME, pmid, exc
                )
                outcome.update(status="failure", error=repr(exc))
            fetched.append(outcome)

    successes = [f for f in fetched if f.get("status") == "success" and f.get("phase") == "efetch"]
    pmid_total = sum(1 for f in fetched if f.get("phase") == "efetch")

    manifest = {
        "dag_id": "regulated_healthcare_dataset_ingest",
        "handler": HANDLER_NAME,
        "dataset_name": resolved["dataset_name"],
        "endpoint_name": resolved["endpoint_name"],
        "location_type": resolved["location_type"],
        "force_refresh": resolved.get("force_refresh", False),
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "url_source": url_source,
        "search_url_count": len(search_urls),
        "pmid_count": pmid_total,
        "success_count": len(successes),
        "fetcher_config": {
            "max_pmids_per_query": MAX_PMIDS_PER_QUERY,
            "inter_request_secs": PUBMED_INTER_REQUEST_SECS,
        },
        "fetched_pages": fetched,
    }
    manifest_path = target / "INGEST_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    if not successes:
        raise RuntimeError(
            f"[{HANDLER_NAME}] no successful efetch responses across {len(search_urls)} "
            f"search url(s); see manifest at {manifest_path}"
        )

    return {"manifest_path": str(manifest_path), "fetched_count": len(successes)}


def _parse_pmids(xml_text: str) -> list[str]:
    """Pull `<IdList><Id>...</Id></IdList>` values out of an esearch response.

    Tolerant: returns [] on parse failure rather than raising. Uses xml.etree
    rather than lxml so this stays stdlib-only — same constraint as the rest
    of the DAG handlers."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    # esearch wraps PMIDs in <IdList><Id>...</Id></IdList>. Some efetch responses
    # also have <Id> elements at deeper nesting (e.g. inside <PubmedArticle>);
    # we only want IdList children to avoid cross-contamination if a caller ever
    # pipes an efetch payload here by mistake.
    pmids: list[str] = []
    for id_list in root.iter("IdList"):
        for el in id_list.iter("Id"):
            text = (el.text or "").strip()
            if text:
                pmids.append(text)
    return pmids
