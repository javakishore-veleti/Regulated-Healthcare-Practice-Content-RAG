# Enabling AWS Bedrock Guardrails (second-line layer)

The default `RAG_GUARDRAILS_BACKEND=regex` runs the 30-rule AHPRA YAML policy — fast, free, gives a clear `rule_id` + rationale per match. Excel Project A's AWS architecture row "Guardrails" names **Amazon Bedrock Guardrails** as the production target. This guide flips RAGMgmt over to a **layered posture**: regex first, then Bedrock — so the regex catches the obvious 30 patterns and Bedrock catches paraphrased / semantic violations the regex misses.

## When to use this

- Production AWS deploy.
- You've seen drafts that the regex passes but a human reviewer would reject ("a patient told us...", "you'll never need treatment again").
- You have IAM access to AWS Bedrock and can provision a guardrail in the console.

## Three modes

| Mode | What runs | When to pick |
|---|---|---|
| `regex` (default) | 30-rule AHPRA YAML policy | Local dev; no AWS deps |
| `bedrock` | Bedrock managed guardrails ONLY | Bedrock-native deploy where regex is redundant (rare — you lose the rationale strings) |
| `layered` | regex FIRST, then Bedrock | **Recommended for production** — regex's free fast pass + Bedrock's semantic catch |

## Prerequisites

- AWS account with Bedrock Guardrails enabled in your region.
- A Bedrock guardrail provisioned in the console with denied topics, content filters, and (optionally) PII filters configured.
- IAM principal has `bedrock:ApplyGuardrail` on the guardrail ARN.
- AWS credentials reachable via the standard chain (env vars, `~/.aws/credentials`, IRSA in EKS, SSO).

## Recommended Bedrock guardrail config

Set up your Bedrock guardrail with policies aimed at the same compliance posture the regex YAML covers:

- **Denied topics:** "Patient testimonials and reviews", "Cure claims", "Medical guarantees", "Best-clinic comparatives".
- **Content filters:** HATE / INSULTS / SEXUAL / VIOLENCE — set to MEDIUM or HIGH for each.
- **Word filters:** Add a custom-word list seeded from your regex policy's banned phrases (best, cure, guaranteed, miracle, etc.) so Bedrock catches the same surface forms in addition to semantic paraphrases.
- **Sensitive information:** PII detectors for `EMAIL`, `PHONE`, `NAME`, `ADDRESS` — flag, don't anonymize, so the violation surfaces in the UI for human review.

## Steps

### 1. Install the optional dep

```sh
cd middleware/RAGMgmt-Service
pip install '.[bedrock-guardrails]'
```

This adds `boto3` if it isn't already installed (shared with `[bedrock-drafter]`, so installing one effectively installs the other).

### 2. Provision the guardrail in AWS

Console: AWS Bedrock → Guardrails → Create. Note the guardrail identifier (e.g. `abcd1234`) and version (`DRAFT` while iterating, a numbered version once published).

### 3. Set the env vars

In `middleware/RAGMgmt-Service/.env`:

```sh
RAG_GUARDRAILS_BACKEND=layered
AWS_BEDROCK_GUARDRAIL_ID=abcd1234
AWS_BEDROCK_GUARDRAIL_VERSION=DRAFT
AWS_BEDROCK_GUARDRAIL_SOURCE=OUTPUT      # OUTPUT scans drafts; INPUT scans prompts
RAG_GUARDRAILS_SHORT_CIRCUIT_ON_CRITICAL=true
```

`short_circuit_on_critical=true` skips the Bedrock call when the regex layer already flagged a CRITICAL violation — the draft is going back to the LLM for regen anyway, no need to pay for another Bedrock call.

### 4. Restart RAGMgmt

```sh
npm run services:stop
npm run services:start
tail -f /tmp/rhc-rag-logs/ragmgmt.log
```

Look for:

```
INFO ... service.guardrails.factory: Using LayeredGuardrailsService (regex → bedrock) — regex catches obvious patterns; Bedrock catches semantic / paraphrased.
```

### 5. Test a generation

```sh
curl -X POST http://localhost:8002/generate \
  -H 'Content-Type: application/json' \
  -d '{"topic":"Marketing copy with a patient story"}' \
  | jq '.respCtxData.guardrails'
```

The `guardrails` block now includes:

- `policy_id` like `layered:regex,bedrock`.
- `violations[]` — each tagged with `source_layer` (`regex` or `bedrock`).
- `layers[]` — per-layer summary with each layer's `policy_id`, `violation_count`, `max_severity`.

The customer portal's existing violations card renders this without changes.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Service log: `Bedrock layer disabled` then `Falling back to regex-only` | dep / config missing | Verify `[bedrock-guardrails]` extra installed AND `AWS_BEDROCK_GUARDRAIL_ID` set |
| Bedrock layer always returns 0 violations on obviously-bad drafts | Guardrail config doesn't have the right denied topics / words | Edit the guardrail in the AWS console and bump to a new version |
| Latency on `/generate` jumped 200–500 ms after enabling | Bedrock call adds round-trip | Acceptable for production; for local-dev iteration, switch back to `regex` |
| Bedrock layer returns violations but `char_start = char_end = 0` | Bedrock returned a content-filter category without surface text — char offsets aren't recoverable | Customer portal renders violations without highlighting in this case; rationale string still surfaces |

## Falling back

```sh
RAG_GUARDRAILS_BACKEND=regex
```

Restart. No code changes.

## Related

- [`middleware/RAGMgmt-Service/service/guardrails/bedrock_guardrails_service.py`](../../middleware/RAGMgmt-Service/service/guardrails/bedrock_guardrails_service.py)
- [`middleware/RAGMgmt-Service/service/guardrails/layered_guardrails_service.py`](../../middleware/RAGMgmt-Service/service/guardrails/layered_guardrails_service.py)
- [`middleware/RAGMgmt-Service/service/guardrails/factory.py`](../../middleware/RAGMgmt-Service/service/guardrails/factory.py)
- [Excel: `RAG_Mastery_Projects.xlsx` → `1_Project_A_Healthcare_Content` → AWS architecture row `Guardrails`]
