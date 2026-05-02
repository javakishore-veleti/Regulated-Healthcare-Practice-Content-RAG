# DataMgmt-Service production Dockerfile.
#
# Build context is the repo root so the image can use the canonical root
# `requirements.txt`. Build commands:
#
#   # local / dev (no cloud secret managers):
#   docker build -f middleware/DataMgmt-Service/Dockerfile -t rhc-datamgmt:dev .
#
#   # AWS deploy:
#   docker build -f middleware/DataMgmt-Service/Dockerfile \
#       --build-arg SECRETS_PROVIDER=aws -t rhc-datamgmt:aws .
#
#   # Azure / GCP analogous: SECRETS_PROVIDER=azure | gcp
#
# The image runs as non-root (`appuser`, uid 10001) per the project's cloud
# portability rules. The healthcheck hits /health on $API_PORT (default 8001).

FROM python:3.12-slim AS runtime

ARG SECRETS_PROVIDER=none

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    API_HOST=0.0.0.0 \
    API_PORT=8001

WORKDIR /app

# OS deps: libpq for psycopg's binary wheels at runtime; curl for healthcheck;
# ca-certificates for outbound TLS to Anthropic / cloud secret managers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps. Root requirements.txt is the union of every middleware
# service's runtime deps — DataMgmt only needs a subset, but installing the
# union is simple, deterministic, and the extra packages cost <100 MB.
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Optional cloud secret-manager extras, gated by build arg.
RUN if [ "$SECRETS_PROVIDER" = "aws" ]; then \
        pip install 'boto3>=1.34'; \
    elif [ "$SECRETS_PROVIDER" = "azure" ]; then \
        pip install 'azure-identity>=1.15' 'azure-keyvault-secrets>=4.7'; \
    elif [ "$SECRETS_PROVIDER" = "gcp" ]; then \
        pip install 'google-cloud-secret-manager>=2.18'; \
    elif [ "$SECRETS_PROVIDER" = "none" ]; then \
        echo "Building without cloud secret-manager extras (literal env vars only)."; \
    else \
        echo "ERROR: SECRETS_PROVIDER must be one of: none, aws, azure, gcp" >&2; \
        exit 1; \
    fi

# Copy the service source. The .dockerignore at the repo root excludes the
# other service's code, the portals, the DAGs, and DevOps/.
COPY middleware/DataMgmt-Service /app

# Non-root user. Fixed uid lets k8s podSecurityPolicy / runAsUser pin to it.
RUN groupadd --system --gid 10001 appgroup \
    && useradd  --system --uid 10001 --gid appgroup --create-home appuser \
    && chown -R appuser:appgroup /app
USER appuser

EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fs "http://localhost:${API_PORT}/health" || exit 1

CMD ["sh", "-c", "uvicorn main:app --host ${API_HOST} --port ${API_PORT}"]
