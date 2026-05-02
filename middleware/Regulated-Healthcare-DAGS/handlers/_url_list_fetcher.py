"""Shared URL-list fetch helper for every per-dataset handler whose ingest is
'pull a curated list of public URLs and save the raw bytes to disk.'

The dataset-specific bits (handler name, fallback URL list, content-type hints,
file extension) are passed in by the caller. Resolution order — same for every
caller — is:

  1. `resolved['urls']` — explicit override on the dag_run.conf
  2. DataMgmt-Service `GET /datasets/{name}/source-urls?only_active=true` — admin-curated
  3. `fallback_urls` — handler-specific last-resort smoke source

Any URL that 4xx/timeouts is recorded in the manifest as a failure; the run as a
whole succeeds as long as at least one URL responds. Writes the manifest in the
same shape as the original AHPRA fetcher so downstream tasks (chunk_via_ragmgmt,
embed_via_pgvector) work unchanged.
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

DEFAULT_USER_AGENT = (
    "RegulatedHealthcareRAG-Bot/0.1 (+https://github.com/javakishore-veleti/"
    "Regulated-Healthcare-Practice-Content-RAG; respectful, public-pages-only)"
)

REQUEST_TIMEOUT_SECS = 20
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


def _resolve_urls(
    resolved: dict[str, Any], fallback_urls: list[str]
) -> tuple[list[str], str]:
    """Returns (urls, source_label). Order: conf.urls → DataMgmt → fallback."""
    if resolved.get("urls"):
        return list(resolved["urls"]), "dag_run_conf"

    curated = _fetch_curated_urls_from_datamgmt(resolved["dataset_name"])
    if curated:
        return curated, "datamgmt_dataset_source_urls"

    return list(fallback_urls), "fallback_default"


def fetch_url_list(
    resolved: dict[str, Any],
    *,
    handler_name: str,
    fallback_urls: list[str],
    file_extension: str = "html",
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict[str, Any]:
    """Generic URL-list fetcher used by every per-dataset handler whose ingest is
    'pull a list of URLs and save the raw bytes.'

    Per-handler customisation:
        handler_name    Recorded in the manifest's `handler` field.
        fallback_urls   Used only when conf.urls is empty AND DataMgmt returns nothing.
        file_extension  e.g., 'html' (default), 'json', 'pdf'.
        user_agent      Override the default polite UA when needed.

    Returns the same `{manifest_path, fetched_count}` shape the orchestrator DAG
    has been consuming since the AHPRA fetcher landed.
    """
    target = Path(resolved["destination_path"])
    target.mkdir(parents=True, exist_ok=True)

    raw_dir = target / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    urls, url_source = _resolve_urls(resolved, fallback_urls)
    LOGGER.info(
        "[%s] fetching %d url(s) for dataset=%s (source=%s)",
        handler_name,
        len(urls),
        resolved["dataset_name"],
        url_source,
    )
    fetched: list[dict[str, Any]] = []

    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})

    for idx, url in enumerate(urls):
        outcome: dict[str, Any] = {"url": url, "index": idx}
        try:
            LOGGER.info("[%s] GET %s", handler_name, url)
            resp = session.get(url, timeout=REQUEST_TIMEOUT_SECS)
            resp.raise_for_status()

            host = urlparse(url).netloc.replace(".", "_")
            fname = f"{idx:03d}_{_slugify(host)}_{_slugify(urlparse(url).path)}.{file_extension}"
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
            LOGGER.warning("[%s] fetch failed for %s: %r", handler_name, url, exc)
            outcome.update(status="failure", error=repr(exc))
        finally:
            fetched.append(outcome)

    successes = [f for f in fetched if f.get("status") == "success"]

    manifest = {
        "dag_id": "regulated_healthcare_dataset_ingest",
        "handler": handler_name,
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
            f"[{handler_name}] all {len(urls)} URL fetches failed; "
            f"see manifest at {manifest_path}"
        )

    return {"manifest_path": str(manifest_path), "fetched_count": len(successes)}
