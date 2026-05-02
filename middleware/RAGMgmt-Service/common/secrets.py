"""Cloud secret-manager resolution.

Settings values like `ANTHROPIC_API_KEY` can be either a literal value (local dev)
or a secret reference resolved at startup against AWS Secrets Manager, Azure Key
Vault, or GCP Secret Manager. Same env var name across all environments —
deployment manifests just point at a different concrete source.

Reference formats:
  aws-sm://<region>/<secret-name>
  azure-kv://<vault-name>/<secret-name>
  gcp-sm://<project>/<secret-name>[/versions/<version>]

Anything else (including None and the empty string) is returned as-is, so this
function is safe to wrap every settings read.

Cloud SDK dependencies are intentionally **optional**. Local dev installs none
of them; cloud deployments add the appropriate one via `pyproject.toml` extras
or the Dockerfile. A reference to a provider whose SDK is missing raises a
clear RuntimeError at startup rather than silently returning the literal
string `aws-sm://...` to downstream code.
"""

from __future__ import annotations

import logging
import re

LOGGER = logging.getLogger(__name__)

_AWS_SM_RE = re.compile(r"^aws-sm://(?P<region>[^/]+)/(?P<name>.+)$")
_AZURE_KV_RE = re.compile(r"^azure-kv://(?P<vault>[^/]+)/(?P<name>.+)$")
_GCP_SM_RE = re.compile(
    r"^gcp-sm://(?P<project>[^/]+)/(?P<name>[^/]+)(?:/versions/(?P<version>.+))?$"
)


def resolve_secret(value: str | None) -> str | None:
    """Resolve a secret reference to its plaintext value, or pass through.

    Returns the input unchanged for literal values, None, or empty strings —
    making this safe to wrap every Settings field that may be sensitive.
    """
    if not value:
        return value

    m = _AWS_SM_RE.match(value)
    if m:
        return _resolve_aws_secret(m["region"], m["name"])

    m = _AZURE_KV_RE.match(value)
    if m:
        return _resolve_azure_secret(m["vault"], m["name"])

    m = _GCP_SM_RE.match(value)
    if m:
        return _resolve_gcp_secret(m["project"], m["name"], m["version"] or "latest")

    return value


def _resolve_aws_secret(region: str, name: str) -> str:
    try:
        import boto3  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "AWS Secrets Manager reference detected but boto3 is not installed. "
            "Install the optional dep: pip install 'boto3>=1.34'"
        ) from exc

    LOGGER.info("Resolving AWS Secrets Manager secret region=%s name=%s", region, name)
    client = boto3.client("secretsmanager", region_name=region)
    resp = client.get_secret_value(SecretId=name)
    if "SecretString" in resp:
        return resp["SecretString"]
    return resp["SecretBinary"].decode("utf-8")


def _resolve_azure_secret(vault: str, name: str) -> str:
    try:
        from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]
        from azure.keyvault.secrets import SecretClient  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "Azure Key Vault reference detected but azure-keyvault-secrets is not "
            "installed. Install the optional deps: "
            "pip install 'azure-identity>=1.15' 'azure-keyvault-secrets>=4.7'"
        ) from exc

    LOGGER.info("Resolving Azure Key Vault secret vault=%s name=%s", vault, name)
    vault_url = f"https://{vault}.vault.azure.net"
    client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
    secret = client.get_secret(name)
    return secret.value or ""


def _resolve_gcp_secret(project: str, name: str, version: str) -> str:
    try:
        from google.cloud import secretmanager  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "GCP Secret Manager reference detected but google-cloud-secret-manager "
            "is not installed. Install the optional dep: "
            "pip install 'google-cloud-secret-manager>=2.18'"
        ) from exc

    LOGGER.info(
        "Resolving GCP Secret Manager secret project=%s name=%s version=%s",
        project,
        name,
        version,
    )
    client = secretmanager.SecretManagerServiceClient()
    secret_path = f"projects/{project}/secrets/{name}/versions/{version}"
    resp = client.access_secret_version(name=secret_path)
    return resp.payload.data.decode("utf-8")
