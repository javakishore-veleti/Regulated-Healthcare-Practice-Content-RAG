# Admin portal

Angular 21 admin portal for the Regulated Healthcare RAG stack. Targets the `DataMgmt-Service` FastAPI backend and (later) a `RAGMgmt-Service`.

## Layout

```
src/app/
  app.ts | app.routes.ts | app.config.ts    Root app + standalone routing
  core/
    api/                                    HTTP client + types
    layout/shell.*                          Top-nav + side-nav shell
  features/
    administration/data-management/
      initial-dataset/                      Tabs per dataset; trigger ingest; history table
    rag-management/                         Placeholder for the parallel top-nav section
```

## Theme

Material 3 with `cyan` primary + `orange` tertiary palettes. Surface tokens are overridden in `src/styles.scss` to a warm off-white (`#fafaf6`) instead of M3's grey-leaning defaults. Top-nav uses a deep teal (`#08434a`) with a warm amber (`#f0b04a`) active accent. **No pure black / pure grey** anywhere in the chrome.

## Running

```sh
# 1. Backend (separate terminal). Postgres must be up: ../../DevOps/Local/docker-all-up.sh
cd ../../middleware/DataMgmt-Service && ./run-local.sh

# 2. This portal
npm start         # runs `ng serve` on http://localhost:4200/ with proxy to localhost:8001
```

`proxy.conf.json` rewrites `/api/*` to `http://127.0.0.1:8001/*` so the portal calls hit the running FastAPI service without CORS handling.

## Routes

| URL | Component |
|---|---|
| `/` | redirects to `/administration/data-management/initial-dataset` |
| `/administration/data-management/initial-dataset` | `InitialDatasetComponent` — Project A datasets, trigger ingest, view history |
| `/rag-management` | `RagManagementComponent` — placeholder |
