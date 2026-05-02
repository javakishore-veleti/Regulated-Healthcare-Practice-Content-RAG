"""Generic ingest entry-point DAG for Project A datasets.

Receives `dag_run.conf` shaped like::

    {
        "dataset_name":   "Public_Regulator_Guidelines",
        "endpoint_name":  "localhost_initial_dataset_default",
        "location_type":  "localhost",
        "location_config": {
            "base_path_under_home": "runtime_data/RAG_Projects/Regulated-Healthcare-RAG/DataSets",
            "latest_ingest_dirname": "Latest_Ingest"
        },
        "dataset_type":  "regulator_guidelines",  # drives fetcher dispatch
        "force_refresh": false
    }

The DAG dispatches by `location_type` for destination handling and by
`dataset_type` for fetcher logic. Each dataset_type maps to a handler module
under `handlers/` (excluded from Airflow's DAG scan via `.airflowignore`); the
single `fetch_for_dataset_type` task picks the right one at runtime so the
downstream `chunk_via_ragmgmt` / `embed_via_pgvector` tasks always run on the
fetched output regardless of which fetcher produced it.

To add a new dataset_type:
  1. Add a handler under `handlers/<name>_fetch.py`.
  2. Register `(dataset_type, handler_filename, callable_name)` in
     `_FETCHER_REGISTRY` below.
  3. (Optional) Seed source URLs via a DataMgmt-Service migration.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from airflow.decorators import dag, task

# DAGs folder is on sys.path inside Airflow, but `handlers/` is excluded from DAG scan.
# Make sure the import resolves against the DAGs folder regardless of working dir.
_DAGS_DIR = os.path.dirname(os.path.abspath(__file__))
if _DAGS_DIR not in sys.path:
    sys.path.insert(0, _DAGS_DIR)

DAG_ID = "regulated_healthcare_dataset_ingest"
TASK_FETCH = "fetch_for_dataset_type"
TASK_CHUNK_VIA_RAGMGMT = "chunk_via_ragmgmt"
TASK_EMBED_VIA_PGVECTOR = "embed_via_pgvector"

# Per Project A's `1_Project_A_Healthcare_Content` worksheet: five datasets, each
# with its own fetcher module. Add entries here to extend.
_FETCHER_REGISTRY: dict[str, tuple[str, str]] = {
    "regulator_guidelines":   ("ahpra_advertising_rules_fetch.py", "fetch_ahpra_advertising_rules"),
    "pubmed":                 ("ncbi_pubmed_fetch.py",            "fetch_ncbi_pubmed"),
    "pmc":                    ("pmc_open_access_fetch.py",        "fetch_pmc_open_access"),
    "pmc_fulltext":           ("pmc_full_text_efetch_fetch.py",   "fetch_pmc_full_text_efetch"),
    "medical_transcriptions": ("kaggle_medical_transcriptions_fetch.py", "fetch_kaggle_medical_transcriptions"),
    "common_crawl":           ("common_crawl_fetch.py",           "fetch_common_crawl"),
}


def _load_handler_module(filename: str):
    """Import a handler module by file path so this works regardless of how
    Airflow's task runner has set up sys.path inside the forked subprocess."""
    import importlib.util
    from pathlib import Path

    handler_path = Path(_DAGS_DIR) / "handlers" / filename
    spec = importlib.util.spec_from_file_location(
        f"rhc_handlers.{filename.replace('.py', '')}", handler_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load handler module at {handler_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _resolve_localhost_path(dataset_name: str, location_config: dict) -> Path:
    base_under_home = location_config.get("base_path_under_home")
    if not base_under_home:
        raise ValueError("location_config.base_path_under_home is required")
    latest_dirname = location_config.get("latest_ingest_dirname", "Latest_Ingest")

    data_root = os.environ.get("RHC_DATA_ROOT") or str(Path.home())
    return Path(data_root) / base_under_home / dataset_name / latest_dirname


@dag(
    dag_id=DAG_ID,
    description=(
        "Generic dataset-ingest entry point for Project A. Dispatches by "
        "endpoint location_type (destination) and dataset_type (fetcher)."
    ),
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=4,
    tags=["regulated-healthcare", "ingest", "project-a"],
)
def regulated_healthcare_dataset_ingest():
    @task
    def resolve_destination(**context) -> dict:
        dag_run = context["dag_run"]
        conf = dict(dag_run.conf or {})

        required = ["dataset_name", "endpoint_name", "location_type", "location_config"]
        missing = [k for k in required if not conf.get(k)]
        if missing:
            raise ValueError(f"dag_run.conf missing required keys: {missing}")

        if conf["location_type"] != "localhost":
            raise NotImplementedError(
                f"location_type={conf['location_type']!r} not implemented yet "
                "in this DAG; add a destination handler."
            )

        target = _resolve_localhost_path(
            dataset_name=conf["dataset_name"],
            location_config=conf["location_config"],
        )

        return {
            "dataset_name": conf["dataset_name"],
            "dataset_type": conf.get("dataset_type"),
            "endpoint_name": conf["endpoint_name"],
            "location_type": conf["location_type"],
            "force_refresh": bool(conf.get("force_refresh", False)),
            "destination_path": str(target),
            "urls": conf.get("urls"),  # optional override for url-list fetchers
        }

    @task(task_id=TASK_FETCH)
    def fetch_for_dataset_type(resolved: dict) -> dict:
        """Dispatch to the dataset_type-specific fetcher. Falls back to a stub
        manifest writer if the dataset_type isn't registered (so downstream
        chunk/embed tasks still see a valid manifest)."""
        dataset_type = resolved.get("dataset_type")
        entry = _FETCHER_REGISTRY.get(dataset_type) if dataset_type else None
        if entry is None:
            return _write_stub_manifest(resolved)
        filename, callable_name = entry
        module = _load_handler_module(filename)
        fn = getattr(module, callable_name)
        return fn(resolved)

    @task(task_id=TASK_CHUNK_VIA_RAGMGMT)
    def chunk_via_ragmgmt(resolved: dict, fetch_result: dict) -> dict:
        # Modular per CLAUDE.md: chunking is its own task downstream of fetch
        # so it can be re-run independently. Reads the manifest the fetch handler
        # wrote. Gracefully no-ops when RAGMGMT_BASE_URL is unset.
        module = _load_handler_module("chunk_via_ragmgmt.py")
        return module.chunk_fetched_pages(resolved)

    @task(task_id=TASK_EMBED_VIA_PGVECTOR)
    def embed_via_pgvector(resolved: dict, chunk_result: dict) -> dict:
        # Modular per CLAUDE.md: embedding is its own task downstream of chunking.
        # Reads chunked/*.json, embeds children with the stub embedder, upserts to
        # pgvector. Gracefully no-ops when RHC_VECTORS_DB_DSN is unset.
        module = _load_handler_module("embed_via_pgvector.py")
        return module.embed_chunked_pages(resolved)

    resolved = resolve_destination()
    fetch_result = fetch_for_dataset_type(resolved)
    chunk_result = chunk_via_ragmgmt(resolved, fetch_result)
    embed_via_pgvector(resolved, chunk_result)


def _write_stub_manifest(resolved: dict) -> dict:
    target = Path(resolved["destination_path"])
    target.mkdir(parents=True, exist_ok=True)

    manifest = {
        "dag_id": DAG_ID,
        "handler": "stub",
        "dataset_name": resolved["dataset_name"],
        "dataset_type": resolved.get("dataset_type"),
        "endpoint_name": resolved["endpoint_name"],
        "location_type": resolved["location_type"],
        "force_refresh": resolved["force_refresh"],
        "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
        "marker": (
            f"stub manifest — no fetcher registered for dataset_type="
            f"{resolved.get('dataset_type')!r}; register one in _FETCHER_REGISTRY"
        ),
    }
    manifest_path = target / "INGEST_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return {"manifest_path": str(manifest_path), "fetched_count": 0}


regulated_healthcare_dataset_ingest()
