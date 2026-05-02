-- Practice voice corpus — the third grounding corpus alongside regulator rules
-- and clinical evidence (per README objectives). Each practice would have its own
-- voice corpus; this seed registers a `Practice_Voice_Sample` placeholder so the
-- retrieval flow has a third corpus to ground from out of the box.
--
-- The actual sample voice content is loaded into `rag_vectors.child_chunk_embeddings`
-- by `middleware/RAGMgmt-Service/scripts/seed_practice_voice.py`, which runs after
-- migrations (see DevOps/Local/docker-all-up.sh).

INSERT INTO system_datasets (dataset_name, dataset_type) VALUES
    ('Practice_Voice_Sample', 'practice_voice')
ON CONFLICT (dataset_name) DO NOTHING;
