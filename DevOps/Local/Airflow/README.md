# Airflow — local

Single-container `airflow standalone` running `apache/airflow:2.10.0-python3.12` (cached locally) for the local-dev stack.

## Wiring

- **Metadata DB:** `airflow` database in the existing `rhc-postgres` instance, reached via `host.docker.internal:5432`. Airflow's own `airflow db migrate` runs on startup.
- **DAGs folder:** `middleware/Regulated-Healthcare-DAGS/` mounted read-only at `/opt/airflow/dags`. This is the project's canonical DAG location per CLAUDE.md.
- **Localhost data root:** the host's `${HOME}/runtime_data` is bind-mounted at the same absolute path inside the container, and `HOME` + `RHC_DATA_ROOT` env vars match the host's value. As a result `Path.home() / "runtime_data" / ...` resolves identically in:
  - the FastAPI `LocalhostStorageHandler` (running on host)
  - the Airflow DAG (running in container)
  No path translation is needed.
- **Executor:** `LocalExecutor` — local-dev only; cloud k8s deploys will use `Celery`/`Kubernetes` executors.
- **UI:** http://localhost:8080 (admin / admin).

## Triggering the ingest DAG manually

```sh
docker exec rhc-airflow airflow dags trigger \
  regulated_healthcare_dataset_ingest \
  --conf '{"dataset_name":"Public_Regulator_Guidelines","endpoint_name":"localhost_initial_dataset_default","location_type":"localhost","location_config":{"base_path_under_home":"runtime_data/RAG_Projects/Regulated-Healthcare-RAG/DataSets","latest_ingest_dirname":"Latest_Ingest"},"force_refresh":false}'
```

Or via REST:

```sh
curl -u admin:admin -X POST http://localhost:8080/api/v1/dags/regulated_healthcare_dataset_ingest/dagRuns \
  -H 'Content-Type: application/json' \
  -d '{"conf":{"dataset_name":"...","endpoint_name":"...", "location_type":"localhost", "location_config":{...}, "force_refresh":false}}'
```

The FastAPI service does not yet trigger this DAG — the existing `/ingest` endpoint still uses the synchronous `LocalhostStorageHandler` stub. The wiring slice that replaces the stub with an Airflow trigger lands next.

## Notes

- `AIRFLOW_UID` env var (default 50000) controls the container user. On Linux you may want to set `AIRFLOW_UID=$(id -u)` to avoid file-ownership surprises in the bind-mounted DAGs / data dirs. macOS Docker Desktop normally handles this transparently.
- Volumes (named): `rhc-airflow-logs` — preserved by default; cleared by `docker-all-down.sh` per the project's volume-removal-by-default policy.
