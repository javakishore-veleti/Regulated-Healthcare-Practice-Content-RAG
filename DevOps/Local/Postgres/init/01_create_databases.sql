-- Bootstrap the three local Postgres databases used by the Regulated Healthcare RAG stack.
--   airflow      Apache Airflow metadata DB
--   rag_app      Application DB (system_datasets, system_datasets_ingest, etc.)
--   rag_vectors  pgvector embeddings store

CREATE DATABASE airflow;
CREATE DATABASE rag_app;
CREATE DATABASE rag_vectors;

-- pgvector is bundled in the pgvector/pgvector image; enable it in the vectors DB.
\c rag_vectors;
CREATE EXTENSION IF NOT EXISTS vector;
