-- Seed the four Project A RAG patterns sourced from
-- 1_Project_A_Healthcare_Content row 9 of RAG_Mastery_Projects.xlsx.

INSERT INTO rag_patterns (pattern_key, display_name, summary, excel_source) VALUES
    (
        'hybrid_rerank',
        'Hybrid search + cross-encoder rerank',
        'Combine lexical (e.g., BM25) and dense retrieval, then rerank top-K with a cross-encoder before passing context to the generator.',
        '1_Project_A_Healthcare_Content row 9'
    ),
    (
        'parent_child_chunking',
        'Parent-child chunking',
        'Retrieve on small child chunks for precision; generate against larger parent chunks for context. Persist parent_id linkage so the parent text can be reconstructed >99% from indexed children.',
        '1_Project_A_Healthcare_Content row 9'
    ),
    (
        'self_rag',
        'Self-RAG faithfulness loop',
        'Critic loop: if a generated draft scores below a faithfulness threshold or trips a compliance flag, regenerate. Faithfulness >= 0.9 on the holdout set is the acceptance bar.',
        '1_Project_A_Healthcare_Content row 9'
    ),
    (
        'output_guardrails',
        'Output guardrails for banned-phrase / forbidden-claim detection',
        'Final output passes through a guardrail layer that blocks regulator-banned phrases (testimonials, "cure", "guaranteed", "best") and forbidden therapeutic claims. 100% known-bad-sample detection is the bar.',
        '1_Project_A_Healthcare_Content row 9'
    );
