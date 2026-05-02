# Vector DBs — local

Status: **placeholder. Image(s) not cached locally — confirm with user before pulling.**

Open question: which OSS vector DB(s) should run locally? The Excel sheet `1_Project_A_Healthcare_Content` lists candidates (e.g., Weaviate, Qdrant, Milvus, Chroma). Pinecone is proprietary — its local equivalent will be one of the OSS options. Decision is deferred until the user picks.

Note: `pgvector` is already available via the local Postgres stack (`rhc-postgres`, database `rag_vectors`), so a subset of patterns from the Excel can already be implemented without standing up an additional vector DB here.
