"""Fetcher for `dataset_type == 'regulator_guidelines'` in Project A.

Imported and called by `regulated_healthcare_dataset_ingest` when the dispatching task
sees a regulator-guidelines dataset. Lives outside the DAGs scan path via the sibling
`.airflowignore` (`^handlers/`) so it is not picked up as a DAG by Airflow's bag.

URL resolution order:
  1. `resolved['urls']` — explicit override on the dag_run.conf
  2. DataMgmt-Service `GET /datasets/{name}/source-urls?only_active=true` — admin-curated
  3. `DEFAULT_REGULATOR_URLS_FALLBACK` — last-resort smoke source (Wikipedia AHPRA article)

The DataMgmt URL is read from `DATAMGMT_BASE_URL`. When unset (e.g., DataMgmt isn't
running), the handler falls back to the hardcoded list rather than failing the run.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

LOGGER = logging.getLogger(__name__)

DEFAULT_REGULATOR_URLS_FALLBACK: list[str] = [
    # Stable smoke source used only if conf.urls is empty AND DataMgmt-Service is
    # unreachable AND the dataset has no curated URLs. Real curation belongs in
    # the dataset_source_urls admin table, not here.
    "https://en.wikipedia.org/wiki/Australian_Health_Practitioner_Regulation_Agency",
]

USER_AGENT = (
    "RegulatedHealthcareRAG-Bot/0.1 (+https://github.com/javakishore-veleti/"
    "Regulated-Healthcare-Practice-Content-RAG; respectful, public-pages-only)"
)

REQUEST_TIMEOUT_SECS = 20
INTER_REQUEST_DELAY_SECS = 0.5
DATAMGMT_LOOKUP_TIMEOUT_SECS = 10


def _slugify(value: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in value)
    safe = safe.strip("_")
    return safe[:120] or "page"


def _fetch_curated_urls_from_datamgmt(dataset_name: str) -> list[str] | None:
    """Pull active source URLs from DataMgmt-Service. Returns None on any failure
    so the caller can fall back to the hardcoded list."""
    base_url = (os.environ.get("DATAMGMT_BASE_URL") or "").rstrip("/")
    if not base_url:
        LOGGER.info(
            "DATAMGMT_BASE_URL not configured; skipping curated source URL lookup."
        )
        return None
    try:
        resp = requests.get(
            f"{base_url}/datasets/{dataset_name}/source-urls",
            params={"only_active": "true"},
            timeout=DATAMGMT_LOOKUP_TIMEOUT_SECS,
        )
        resp.raise_for_status()
        ctx = resp.json().get("respCtxData") or {}
        rows = ctx.get("source_urls") or []
        urls = [r["url"] for r in rows if r.get("url")]
        LOGGER.info(
            "Loaded %d curated source URL(s) from DataMgmt for dataset=%s",
            len(urls),
            dataset_name,
        )
        return urls if urls else None
    except (requests.RequestException, ValueError, KeyError) as exc:
        LOGGER.warning(
            "DataMgmt curated-URL lookup failed for dataset=%s: %r — falling back",
            dataset_name,
            exc,
        )
        return None


def _resolve_urls(resolved: dict[str, Any]) -> tuple[list[str], str]:
    """Returns (urls, source_label). Order: conf.urls → DataMgmt → fallback."""
    if resolved.get("urls"):
        return list(resolved["urls"]), "dag_run_conf"

    curated = _fetch_curated_urls_from_datamgmt(resolved["dataset_name"])
    if curated:
        return curated, "datamgmt_dataset_source_urls"

    return list(DEFAULT_REGULATOR_URLS_FALLBACK), "fallback_default"


def fetch_ahpra_advertising_rules(resolved: dict[str, Any]) -> dict[str, Any]:
    """Fetch each URL from `resolved['urls']` (or DEFAULT_REGULATOR_URLS) into the
    dataset's `Latest_Ingest/` folder, save raw response bodies, and write a manifest.

    Returns a dict mirroring what the stub manifest writer returned, plus per-URL
    fetch outcomes under `fetched_pages`.
    """
    target = Path(resolved["destination_path"])
    target.mkdir(parents=True, exist_ok=True)

    raw_dir = target / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    urls, url_source = _resolve_urls(resolved)
    LOGGER.info("Fetching %d url(s) for dataset=%s (source=%s)", len(urls), resolved["dataset_name"], url_source)
    fetched: list[dict[str, Any]] = []

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    for idx, url in enumerate(urls):
        outcome: dict[str, Any] = {"url": url, "index": idx}
        try:
            LOGGER.info("Fetching %s", url)
            resp = session.get(url, timeout=REQUEST_TIMEOUT_SECS)
            resp.raise_for_status()

            host = urlparse(url).netloc.replace(".", "_")
            fname = f"{idx:03d}_{_slugify(host)}_{_slugify(urlparse(url).path)}.html"
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
            LOGGER.warning("Fetch failed for %s: %r", url, exc)
            outcome.update(status="failure", error=repr(exc))
        finally:
            fetched.append(outcome)

    successes = [f for f in fetched if f.get("status") == "success"]

    manifest = {
        "dag_id": "regulated_healthcare_dataset_ingest",
        "handler": "ahpra_advertising_rules_fetch",
        "dataset_name": resolved["dataset_name"],
        "endpoint_name": resolved["endpoint_name"],
        "location_type": resolved["location_type"],
        "force_refresh": resolved.get("force_refresh", False),
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "url_source": url_source,
        "url_count": len(urls),
        "success_count": len(successes),
        "fetched_pages": fetched,
    }
    manifest_path = target / "INGEST_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    if not successes:
        raise RuntimeError(
            f"All {len(urls)} URL fetches failed; see manifest at {manifest_path}"
        )

    return {"manifest_path": str(manifest_path), "fetched_count": len(successes)}
