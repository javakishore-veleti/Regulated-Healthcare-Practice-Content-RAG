# Airflow — local

Status: **placeholder, compose not built yet.**

Image is already cached locally (`apache/airflow:2.10.0-python3.12`), so this folder is not blocked by image availability — it is the next planned slice after Postgres.

When implemented, this Airflow instance will:
- Use the shared local Postgres (`rhc-postgres`) `airflow` database for metadata.
- Mount `middleware/Regulated-Healthcare-DAGS/` as the DAGs folder (per the project's DAG-location convention).
- Default to `LocalExecutor` (no separate worker / Redis required) unless we explicitly switch to Celery later.
