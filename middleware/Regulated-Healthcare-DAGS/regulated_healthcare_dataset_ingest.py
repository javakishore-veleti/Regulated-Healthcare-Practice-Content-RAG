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
        "force_refresh":  false
    }

Per the project's endpoint abstraction, the DAG dispatches by `location_type` for
destination handling and by `dataset_type` for fetcher logic. Only `localhost` is
implemented as a destination. Per-dataset-type handlers live in `handlers/` (excluded
from Airflow's DAG scan via `.airflowignore`); add a new handler module + a branch
case in `dispatch_by_dataset_type` to extend.
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

DATASET_TYPE_REGULATOR_GUIDELINES = "regulator_guidelines"
TASK_FETCH_REGULATOR_GUIDELINES = "fetch_regulator_guidelines"
TASK_WRITE_STUB_MANIFEST = "write_stub_manifest"


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
            "dataset_type": conf.get("dataset_type"),  # pulled from FastAPI side
            "endpoint_name": conf["endpoint_name"],
            "location_type": conf["location_type"],
            "force_refresh": bool(conf.get("force_refresh", False)),
            "destination_path": str(target),
            "urls": conf.get("urls"),  # optional override for url-list fetchers
        }

    @task.branch
    def dispatch_by_dataset_type(resolved: dict) -> str:
        if resolved.get("dataset_type") == DATASET_TYPE_REGULATOR_GUIDELINES:
            return TASK_FETCH_REGULATOR_GUIDELINES
        return TASK_WRITE_STUB_MANIFEST

    @task(task_id=TASK_FETCH_REGULATOR_GUIDELINES)
    def fetch_regulator_guidelines(resolved: dict) -> dict:
        # Load the sibling handler by file path so this works regardless of how
        # Airflow's task runner has set up sys.path inside the forked subprocess.
        import importlib.util
        from pathlib import Path

        handler_path = Path(_DAGS_DIR) / "handlers" / "ahpra_advertising_rules_fetch.py"
        spec = importlib.util.spec_from_file_location(
            "rhc_handlers.ahpra_advertising_rules_fetch", handler_path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"could not load handler module at {handler_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        return module.fetch_ahpra_advertising_rules(resolved)

    @task(task_id=TASK_WRITE_STUB_MANIFEST)
    def write_stub_manifest(resolved: dict) -> dict:
        target = Path(resolved["destination_path"])
        target.mkdir(parents=True, exist_ok=True)

        manifest = {
            "dag_id": DAG_ID,
            "handler": "stub",
            "dataset_name": resolved["dataset_name"],
            "endpoint_name": resolved["endpoint_name"],
            "location_type": resolved["location_type"],
            "force_refresh": resolved["force_refresh"],
            "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
            "marker": (
                "stub manifest — no per-dataset-type fetcher implemented yet for this "
                "dataset_type; replaces slice by slice"
            ),
        }
        manifest_path = target / "INGEST_MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        return {"manifest_path": str(manifest_path)}

    resolved = resolve_destination()
    branch = dispatch_by_dataset_type(resolved)
    fetch_branch = fetch_regulator_guidelines(resolved)
    stub_branch = write_stub_manifest(resolved)

    branch >> [fetch_branch, stub_branch]


regulated_healthcare_dataset_ingest()
