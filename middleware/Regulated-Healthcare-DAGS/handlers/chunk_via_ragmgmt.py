"""Chunking handler — calls RAGMgmt-Service /chunk for each fetched page in an
ingest run and writes parent/child chunks to `Latest_Ingest/chunked/`.

Gracefully no-ops when `RAGMGMT_BASE_URL` is unset (so the ingest pipeline still
succeeds in environments without RAGMgmt-Service running). Uses stdlib only —
no extra deps beyond what apache/airflow ships with.
"""

from __future__ import annotations

import html as _html_module
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)

RAGMGMT_TIMEOUT_SECS = 30
DEFAULT_PARENT_SIZE = 1500
DEFAULT_CHILD_SIZE = 256

# Strip <script>...</script> and <style>...</style> wholesale, then strip remaining
# tags. Robust against HTML void elements (<meta>, <link>) where stdlib HTMLParser's
# start/end tag accounting goes off-by-one.
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
_NOSCRIPT_RE = re.compile(r"<noscript\b[^>]*>.*?</noscript>", re.DOTALL | re.IGNORECASE)
_BLOCK_RE = re.compile(r"</(p|div|section|article|header|footer|li|h[1-6]|br)\s*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_text(html_str: str) -> str:
    s = _SCRIPT_RE.sub(" ", html_str)
    s = _STYLE_RE.sub(" ", s)
    s = _NOSCRIPT_RE.sub(" ", s)
    # Insert a paragraph boundary at the close of common block elements so the
    # parent-splitter sees real paragraph structure after we drop tags.
    s = _BLOCK_RE.sub("\n\n", s)
    s = _TAG_RE.sub(" ", s)
    s = _html_module.unescape(s)
    lines = [" ".join(line.split()) for line in s.splitlines()]
    meaningful = [line for line in lines if line]
    return "\n\n".join(meaningful)


def chunk_fetched_pages(resolved: dict[str, Any]) -> dict[str, Any]:
    """Read the ingest manifest, call /chunk for each successfully fetched page,
    write per-page chunks JSON files under `Latest_Ingest/chunked/`."""
    base_url = (os.environ.get("RAGMGMT_BASE_URL") or "").rstrip("/")
    target = Path(resolved["destination_path"])
    manifest_path = target / "INGEST_MANIFEST.json"

    if not manifest_path.is_file():
        return {"status": "skipped", "reason": f"manifest not found at {manifest_path}"}

    manifest = json.loads(manifest_path.read_text())
    fetched: list[dict] = manifest.get("fetched_pages", [])

    if not base_url:
        manifest["chunking"] = {
            "status": "skipped",
            "reason": "RAGMGMT_BASE_URL not configured in this environment",
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        return manifest["chunking"]

    chunked_dir = target / "chunked"
    chunked_dir.mkdir(parents=True, exist_ok=True)

    per_page: list[dict[str, Any]] = []
    total_parents = 0
    total_children = 0

    for outcome in fetched:
        idx = outcome.get("index", -1)
        if outcome.get("status") != "success" or not outcome.get("saved_to"):
            per_page.append({"index": idx, "status": "skipped_no_raw_file"})
            continue

        raw_path = target / outcome["saved_to"]
        text = _html_to_text(raw_path.read_text(encoding="utf-8", errors="replace"))
        if not text.strip():
            per_page.append({"index": idx, "status": "skipped_empty_text"})
            continue

        try:
            resp = requests.post(
                f"{base_url}/chunk",
                json={
                    "text": text,
                    "parent_size_chars": DEFAULT_PARENT_SIZE,
                    "child_size_chars": DEFAULT_CHILD_SIZE,
                },
                timeout=RAGMGMT_TIMEOUT_SECS,
            )
            resp.raise_for_status()
            ctx = resp.json().get("respCtxData") or {}
        except (requests.RequestException, ValueError) as exc:
            LOGGER.warning("Chunking failed for page %s: %r", idx, exc)
            per_page.append({"index": idx, "status": "failure", "error": repr(exc)})
            continue

        out_path = chunked_dir / f"{idx:03d}_chunks.json"
        out_path.write_text(json.dumps(ctx, indent=2) + "\n")

        parents = ctx.get("parent_count", 0)
        children = ctx.get("child_count", 0)
        total_parents += parents
        total_children += children
        per_page.append(
            {
                "index": idx,
                "status": "success",
                "parent_count": parents,
                "child_count": children,
                "saved_to": str(out_path.relative_to(target)),
            }
        )

    chunking_summary = {
        "status": "ok",
        "ragmgmt_base_url": base_url,
        "pages": per_page,
        "total_parents": total_parents,
        "total_children": total_children,
    }
    manifest["chunking"] = chunking_summary
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return chunking_summary
