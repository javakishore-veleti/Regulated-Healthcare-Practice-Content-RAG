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

Per the project's endpoint abstraction the DAG dispatches by `location_type`. Only the
`localhost` handler is implemented in this slice — it writes a JSON manifest into the
dataset's `Latest_Ingest/` folder. Per-dataset fetchers (AHPRA scraper, PubMed filter,
etc.) replace the stub slice by slice; the dispatch table below is the place to extend.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from airflow.decorators import dag, task

DAG_ID = "regulated_healthcare_dataset_ingest"


def _resolve_localhost_path(dataset_name: str, location_config: dict) -> Path:
    base_under_home = location_config.get("base_path_under_home")
    if not base_under_home:
        raise ValueError("location_config.base_path_under_home is required")
    latest_dirname = location_config.get("latest_ingest_dirname", "Latest_Ingest")

    # RHC_DATA_ROOT (set by the Airflow compose) makes Path.home() match the host's HOME
    # even though Airflow runs as user `airflow` in the container. Fall back to the
    # process home if the env var is unset (e.g., when invoked outside the container).
    data_root = os.environ.get("RHC_DATA_ROOT") or str(Path.home())
    return Path(data_root) / base_under_home / dataset_name / latest_dirname


@dag(
    dag_id=DAG_ID,
    description=(
        "Generic dataset-ingest entry point for Project A. Dispatches by "
        "endpoint location_type; localhost handler writes a manifest stub."
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
                "in this DAG; add a handler under the dispatch table."
            )

        target = _resolve_localhost_path(
            dataset_name=conf["dataset_name"],
            location_config=conf["location_config"],
        )

        return {
            "dataset_name": conf["dataset_name"],
            "endpoint_name": conf["endpoint_name"],
            "location_type": conf["location_type"],
            "force_refresh": bool(conf.get("force_refresh", False)),
            "destination_path": str(target),
        }

    @task
    def write_manifest(resolved: dict) -> dict:
        target = Path(resolved["destination_path"])
        target.mkdir(parents=True, exist_ok=True)

        manifest = {
            "dag_id": DAG_ID,
            "dataset_name": resolved["dataset_name"],
            "endpoint_name": resolved["endpoint_name"],
            "location_type": resolved["location_type"],
            "force_refresh": resolved["force_refresh"],
            "ingested_at_utc": datetime.now(timezone.utc).isoformat(),
            "marker": (
                "stub manifest written by regulated_healthcare_dataset_ingest; "
                "per-dataset fetchers replace this content slice by slice"
            ),
        }
        manifest_path = target / "INGEST_MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        return {"manifest_path": str(manifest_path)}

    write_manifest(resolve_destination())


regulated_healthcare_dataset_ingest()
