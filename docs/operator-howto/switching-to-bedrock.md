# Switching to Bedrock for drafting

The README's stated production drafter target is Claude Opus served via AWS Bedrock. The default `LLM_DRAFTER=auto` uses the direct Anthropic Messages API when `ANTHROPIC_API_KEY` is set; this guide flips RAGMgmt-Service over to Bedrock instead.

## When to use this

- Production deploy on AWS — Bedrock keeps the model invocations inside your VPC and rolls into AWS billing.
- You already have IAM policies / Bedrock model access provisioned.
- Local dev where you'd rather authenticate via SSO/IAM than handle a literal API key.

## Prerequisites

- AWS account with Bedrock enabled in your region.
- A Claude inference profile or model ID in Bedrock (e.g. `us.anthropic.claude-opus-4-7-...-v1:0`).
- AWS credentials reachable via the standard chain — env vars, `~/.aws/credentials`, IRSA in EKS, or SSO. We do not store credentials in `.env`.

## Steps

### 1. Install the optional dep

```sh
cd middleware/RAGMgmt-Service
pip install '.[bedrock-drafter]'
```

This adds `boto3>=1.34` to your venv. The `bedrock_drafter` module's `import boto3` is lazy (inside `__init__`), so the rest of the service still loads even when the dep isn't installed.

### 2. Set the env vars

In `middleware/RAGMgmt-Service/.env`:

```sh
LLM_DRAFTER=bedrock
BEDROCK_MODEL_ID=us.anthropic.claude-opus-4-7-20250605-v1:0   # your real model ID
BEDROCK_REGION=us-east-1
```

`BEDROCK_MODEL_ID` is required when `LLM_DRAFTER=bedrock` — empty model_id falls back to stub with a clear WARNING in the service log.

### 3. Verify your AWS chain

```sh
aws sts get-caller-identity   # should print your IAM principal
aws bedrock list-foundation-models --region us-east-1 \
    | jq '.modelSummaries[] | select(.modelId | startswith("anthropic")) | .modelId'
```

If `get-caller-identity` fails, your AWS chain isn't reachable from your shell — fix that first (the FastAPI process inherits the same chain).

### 4. Restart the service

```sh
npm run services:stop
npm run services:start
tail -f /tmp/rhc-rag-logs/ragmgmt.log
```

Look for:

```
INFO ... main: Using BedrockDrafter with model=us.anthropic.claude-opus-4-7-... region=us-east-1
```

If you instead see `falling back to stub`, check the WARNING immediately above — it'll name the missing piece (boto3 not installed, or BEDROCK_MODEL_ID unset).

### 5. Test a generation

```sh
curl -X POST http://localhost:8002/generate \
  -H 'Content-Type: application/json' \
  -d '{"topic":"AHPRA telehealth advertising","top_k_per_corpus":2}' | jq '.respCtxData.generator'
```

Should print `"bedrock_anthropic_claude_drafter"`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Service log: `LLM_DRAFTER=bedrock but boto3 not installed` | Optional dep missing | `pip install '.[bedrock-drafter]'` |
| Service log: `BEDROCK_MODEL_ID is unset; falling back to stub` | Env var typo / not loaded | Verify `.env` is in `middleware/RAGMgmt-Service/` and has the var |
| Service log: `Using BedrockDrafter` but request hangs / fails with `AccessDeniedException` | IAM principal lacks `bedrock:InvokeModel` on the model | Add the IAM policy; cross-region inference profiles need access in BOTH the source and target regions |
| Request succeeds but returns `Insufficient grounded sources` | The drafter is wired correctly; the issue is upstream retrieval has zero hits | Check `respCtxData.retrieval_meta.corpora_present` — likely all three are missing |

## Falling back

To revert without un-installing the dep, just unset / change the var:

```sh
LLM_DRAFTER=auto    # uses Anthropic when ANTHROPIC_API_KEY is set
LLM_DRAFTER=stub    # forces the deterministic stub composer
```

Restart the service. No code changes.

## Related

- [`middleware/RAGMgmt-Service/service/drafters/bedrock_drafter.py`](../../middleware/RAGMgmt-Service/service/drafters/bedrock_drafter.py) — implementation
- [`middleware/RAGMgmt-Service/service/drafters/factory.py`](../../middleware/RAGMgmt-Service/service/drafters/factory.py) — selection logic
- [README — Optional extras](../../README.md#optional-extras-heavy--opt-in-deps) — full extras matrix
