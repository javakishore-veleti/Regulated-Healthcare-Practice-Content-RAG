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

# Pipeline:
#   1. _extract_main_content  — prefer <main>, then <article>; falls through to
#      the whole document when neither is present (older / static AHPRA pages).
#   2. _strip_chrome          — drop nav/header/footer/aside/form/button/dialog,
#      and the script/style/noscript scaffolding. These almost never carry
#      regulator content; keeping them dilutes BM25 (high-rarity boilerplate
#      tokens inflate scores) and dense retrieval (semantic dilution).
#   3. _html_to_plain_text    — paragraph-aware tag strip + whitespace normalize.
# Robust against HTML void elements (<meta>, <link>) where stdlib HTMLParser's
# start/end tag accounting goes off-by-one. Pure stdlib.

_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script>", re.DOTALL | re.IGNORECASE)
_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
_NOSCRIPT_RE = re.compile(r"<noscript\b[^>]*>.*?</noscript>", re.DOTALL | re.IGNORECASE)

_MAIN_RE = re.compile(r"<main\b[^>]*>(.*?)</main>", re.DOTALL | re.IGNORECASE)
_ARTICLE_RE = re.compile(r"<article\b[^>]*>(.*?)</article>", re.DOTALL | re.IGNORECASE)

# Each entry strips the entire tagged region from the HTML (open through close),
# along with anything the tag wrapped. <form> covers search/login boxes;
# <button>/<dialog> cover modal/cookie chrome; <aside> is the conventional sidebar.
_CHROME_TAG_NAMES = ("nav", "header", "footer", "aside", "form", "button", "dialog")
_CHROME_REs = [
    re.compile(rf"<{tag}\b[^>]*>.*?</{tag}>", re.DOTALL | re.IGNORECASE)
    for tag in _CHROME_TAG_NAMES
]

# Common boilerplate by class/id substring — non-exhaustive, but covers what
# AHPRA / FTC / PMC actually serve. Matches a containing element by class/id and
# strips the entire tag pair.
_CHROME_CLASS_PATTERNS = (
    r'class="[^"]*\b(?:breadcrumb|skip-link|cookie|cookies|site-search|'
    r'masthead|sidenav|sidebar|menu-toggle|backtotop)\b[^"]*"'
)
_CHROME_BY_CLASS_RE = re.compile(
    rf'<(div|section|ul|ol|nav)\b[^>]*{_CHROME_CLASS_PATTERNS}[^>]*>.*?</\1>',
    re.DOTALL | re.IGNORECASE,
)

# Heading-preserve pre-pass: convert <h1>..<h6> tags to markdown `# `..`###### `
# BEFORE the generic tag stripper runs. The chunker (chunking_service.py) reads
# `## Heading` lines and attaches them as `parent_heading` to subsequent parents,
# so the regulator-corpus ingest gets section anchors per Excel Task 4.
_HX_RE = re.compile(
    r"<h([1-6])\b[^>]*>(.*?)</h\1>",
    re.DOTALL | re.IGNORECASE,
)

_BLOCK_RE = re.compile(
    r"</(p|div|section|article|header|footer|li|br|tr)\s*>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")

# A "main content" candidate must yield at least this much text; otherwise we
# treat the <main> / <article> match as a false positive (some sites wrap the
# header rail in <main>) and fall back to the chrome-stripped whole document.
_MIN_MAIN_CONTENT_CHARS = 200


def _extract_main_content(html_str: str) -> str:
    """Return the inner HTML of the first <main> or <article> region that
    contains a meaningful amount of content; otherwise return the input."""
    for pattern in (_MAIN_RE, _ARTICLE_RE):
        match = pattern.search(html_str)
        if not match:
            continue
        candidate = match.group(1)
        # Quick proxy for "is there real content here?" — strip tags inline and
        # measure non-whitespace chars. Cheap, doesn't recurse the full pipeline.
        approx_text = _TAG_RE.sub(" ", candidate)
        if sum(1 for c in approx_text if not c.isspace()) >= _MIN_MAIN_CONTENT_CHARS:
            return candidate
    return html_str


def _strip_chrome(html_str: str) -> str:
    s = _SCRIPT_RE.sub(" ", html_str)
    s = _STYLE_RE.sub(" ", s)
    s = _NOSCRIPT_RE.sub(" ", s)
    for chrome_re in _CHROME_REs:
        s = chrome_re.sub(" ", s)
    s = _CHROME_BY_CLASS_RE.sub(" ", s)
    return s


def _convert_headings_to_markdown(html_str: str) -> str:
    """Replace `<h2>Foo</h2>` → `\n\n## Foo\n\n` (and h1..h6 analogously) so
    the chunker sees markdown heading boundaries. Inner-tag content is
    preserved as plain text (the generic tag stripper handles any nested
    inline tags afterward)."""
    def _sub(match):
        level = int(match.group(1))
        inner = match.group(2)
        # Strip any nested inline tags from the heading text.
        text = _TAG_RE.sub(" ", inner)
        text = " ".join(text.split())
        return f"\n\n{'#' * level} {text}\n\n"
    return _HX_RE.sub(_sub, html_str)


def _html_to_plain_text(html_str: str) -> str:
    # First convert headings to markdown so they survive the generic tag
    # stripper as `## Heading` lines. The chunker uses these as section anchors.
    s = _convert_headings_to_markdown(html_str)
    # Insert a paragraph boundary at the close of common block elements so the
    # parent-splitter sees real paragraph structure after we drop tags.
    s = _BLOCK_RE.sub("\n\n", s)
    s = _TAG_RE.sub(" ", s)
    s = _html_module.unescape(s)
    lines = [" ".join(line.split()) for line in s.splitlines()]
    meaningful = [line for line in lines if line]
    return "\n\n".join(meaningful)


def _html_to_text(html_str: str) -> str:
    """Pipeline: prefer-main-content → strip chrome → tags → normalize whitespace.

    Pulled out for testability (see DAG-side unit smoke in this commit's diff)
    and so a future feed (PMC XML, JSON-LD) can swap stages without touching
    chunk_fetched_pages."""
    main = _extract_main_content(html_str)
    chrome_stripped = _strip_chrome(main)
    return _html_to_plain_text(chrome_stripped)


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
