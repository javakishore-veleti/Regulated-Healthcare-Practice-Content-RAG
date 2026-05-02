"""Fetcher for `dataset_type == 'regulator_guidelines'` in Project A.

Imported and called by `regulated_healthcare_dataset_ingest` when the dispatching task
sees a regulator-guidelines dataset. Lives outside the DAGs scan path via the sibling
`.airflowignore` (`^handlers/`) so it is not picked up as a DAG by Airflow's bag.

Default URL list intentionally minimal (one stable Wikipedia article on AHPRA) so the
end-to-end ingest can be exercised without coupling this slice to a curated regulator
URL list. The next slice introduces a source-URL admin UI; once that lands, the
default list will move into config-driven storage and the URLs below will be removed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

LOGGER = logging.getLogger(__name__)

DEFAULT_REGULATOR_URLS: list[str] = [
    # Stable, public, CC-BY-SA — used as a smoke source while the source-URL admin UI
    # is built. Replace with curated AHPRA / FTC / GMC pages in a follow-up slice.
    "https://en.wikipedia.org/wiki/Australian_Health_Practitioner_Regulation_Agency",
]

USER_AGENT = (
    "RegulatedHealthcareRAG-Bot/0.1 (+https://github.com/javakishore-veleti/"
    "Regulated-Healthcare-Practice-Content-RAG; respectful, public-pages-only)"
)

REQUEST_TIMEOUT_SECS = 20
INTER_REQUEST_DELAY_SECS = 0.5


def _slugify(value: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in value)
    safe = safe.strip("_")
    return safe[:120] or "page"


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

    urls: list[str] = resolved.get("urls") or DEFAULT_REGULATOR_URLS
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
