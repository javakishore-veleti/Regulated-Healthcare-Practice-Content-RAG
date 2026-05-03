"""eval — Excel Project A Task 14: golden triples + RAG triad evaluator.

The harness runs each (clinic_profile, topic, expected_citations) triple
through the live RAG pipeline (rag_iface CLI shape) and scores three
metrics per the README's acceptance criteria:

  * Faithfulness          ≥ 0.90 — every claim grounded in retrieved citations
  * Context precision     ≥ 0.75 — retrieved citations are relevant to the topic
  * Answer relevance      ≥ 0.85 — the draft addresses the topic

Faithfulness re-uses the existing FaithfulnessService (token-overlap
scorer; the same one the live regenerate loop uses). Context precision
and answer relevance ship as stdlib heuristics today; production
deployments swap in Ragas's LLM-as-judge versions via an opt-in extra
without touching the harness orchestration.

The HTML report writes a per-triple breakdown + aggregate verdict that
pairs cleanly with the Langfuse traces the same /generate calls emitted —
operators can drill from the eval report row into the exact trace.
"""

__all__ = []
