"""Fetcher for `dataset_type == 'common_crawl'` (Common Crawl filtered subset).

Pulls Common Crawl's documentation / index URLs. The actual ~3 GB allied-health
sample is built by a downstream pipeline that filters CC's WARC archives to
allied-health domains — that's heavy and lives in a separate slice. This
handler is the thin "ingest the docs + landing pages" stub.
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


HANDLER_NAME = "common_crawl_fetch"

DEFAULT_COMMON_CRAWL_URLS_FALLBACK: list[str] = [
    "https://commoncrawl.org/get-started",
    "https://commoncrawl.org/the-data/",
]


def fetch_common_crawl(resolved: dict[str, Any]) -> dict[str, Any]:
    return _url_list_fetcher.fetch_url_list(
        resolved,
        handler_name=HANDLER_NAME,
        fallback_urls=DEFAULT_COMMON_CRAWL_URLS_FALLBACK,
    )
