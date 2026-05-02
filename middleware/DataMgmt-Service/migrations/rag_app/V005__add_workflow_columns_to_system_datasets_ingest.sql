-- Persist Airflow (or any future workflow engine) run identifiers on each ingest row,
-- so the admin portal can deep-link from a history row to the Airflow UI run page.
-- Both columns are nullable: cache-hit rows have no workflow run, and rows created
-- before this migration retain NULL.

ALTER TABLE system_datasets_ingest
    ADD COLUMN workflow_dag_id VARCHAR(200),
    ADD COLUMN workflow_run_id VARCHAR(300);

CREATE INDEX idx_sdi_workflow_run_id ON system_datasets_ingest (workflow_run_id);

COMMENT ON COLUMN system_datasets_ingest.workflow_dag_id IS 'DAG id (currently Airflow). NULL when the run was a cache-hit short-circuit or a future synchronous in-process handler.';
COMMENT ON COLUMN system_datasets_ingest.workflow_run_id IS 'Workflow engine run id (currently Airflow dag_run_id). NULL when no workflow was triggered.';
