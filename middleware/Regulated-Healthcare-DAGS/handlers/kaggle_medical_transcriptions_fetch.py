"""Fetcher for `dataset_type == 'medical_transcriptions'`
(Kaggle: tboyle10/medicaltranscriptions).

Special case: Kaggle datasets require an authenticated Kaggle API key and
explicit T&C acceptance per dataset. This handler does NOT attempt to pull the
~1 GB CSV directly — it ingests the dataset's public landing page (which is
freely viewable without auth) so the corpus's licensing + schema are recorded.

A real, auth-aware Kaggle fetcher will land in a separate slice once we wire
the `KAGGLE_USERNAME` / `KAGGLE_KEY` secret pair through the deployment
manifest. Per the project's compliance posture, we don't bake auth into the
default fetcher — explicit opt-in is required.
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


HANDLER_NAME = "kaggle_medical_transcriptions_fetch"

DEFAULT_KAGGLE_URLS_FALLBACK: list[str] = [
    "https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions",
]


def fetch_kaggle_medical_transcriptions(resolved: dict[str, Any]) -> dict[str, Any]:
    return _url_list_fetcher.fetch_url_list(
        resolved,
        handler_name=HANDLER_NAME,
        fallback_urls=DEFAULT_KAGGLE_URLS_FALLBACK,
    )
