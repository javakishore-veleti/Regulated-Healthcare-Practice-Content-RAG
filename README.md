# Regulated-Healthcare-Practice-Content-RAG
Allied-health practices in regulated jurisdictions (e.g., AU under AHPRA, US under FTC health-claim rules) need SEO content that complies with advertising rules forbidding testimonials, misleading therapeutic claims, and unverified efficacy statements.

## RAG GOAL
Ground every generated draft in (a) the public regulator's published advertising rules, (b) the practice's own voice corpus, (c) open-access clinical evidence.

## Why RAG?
A general LLM can produce a regulatory breach in the first paragraph. RAG forces every claim to map to a retrievable, citable source from a vetted corpus, with a guardrail layer for banned phrases.

## Patterns
- Hybrid search + cross-encoder rerank
- Parent-child chunking
- Self-RAG faithfulness loop
- Output guardrails for banned-phrase / forbidden-claim detection

## Primary observability
- Langfuse (self-hostable, free, OSS) — captures prompt/completion, retrieved-chunk metadata, faithfulness scores per turn

## Secondary observability
- OpenTelemetry GenAI semantic conventions emitted to any OTLP-compatible backend (Grafana Tempo / Honeycomb)


## AWS Architecture
