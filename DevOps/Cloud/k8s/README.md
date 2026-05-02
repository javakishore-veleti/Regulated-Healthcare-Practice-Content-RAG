# Cloud k8s manifests

Generic, kustomize-friendly k8s manifests for the FastAPI middleware services. Designed to deploy unchanged on **AWS EKS, Azure AKS, or GCP GKE** — only the per-cloud overlay differs.

## What's here today

```
DevOps/Cloud/k8s/
└── base/
    ├── namespace.yaml
    ├── datamgmt-{configmap,secret.example,deployment,service}.yaml
    ├── ragmgmt-{configmap,secret.example,deployment,service}.yaml
    ├── ingress.yaml                  # path-routed: /api/{patterns,chunk,...} → ragmgmt; /api/* → datamgmt
    └── kustomization.yaml
```

Each Deployment has:
- 2 replicas, RollingUpdate (`maxSurge: 1, maxUnavailable: 0`)
- `runAsNonRoot: true, runAsUser: 10001` (matches the Dockerfile)
- `readOnlyRootFilesystem: true` + tmpfs at `/tmp`
- `seccompProfile: RuntimeDefault`, all caps dropped, no privilege escalation
- Liveness + readiness probes on `/health`
- Resource requests/limits tuned for first-look (revise per environment)
- Env from a ConfigMap (non-secret) and a Secret (sensitive)
- HorizontalPodAutoscaler (CPU 70%, 2–10 replicas)

## What's NOT here

By design, the `base/` is cloud-agnostic. The following are added per overlay (or by an existing platform-team chart):

| Concern | Per-cloud add-on |
|---|---|
| **Postgres + pgvector** | Managed: AWS RDS (postgres + `pgvector` extension), Azure Database for PostgreSQL, GCP Cloud SQL |
| **Airflow** | Managed: Amazon MWAA, Azure Data Factory + Astronomer, GCP Cloud Composer |
| **Static SPA portals** | nginx Deployment with the `dist/` baked in (separate slice — Dockerfiles for the portals + their own k8s manifests) |
| **Ingress controller** | AWS ALB Ingress / Azure AGIC / GCP GCE Ingress — set `ingressClassName` and the cloud-specific annotations in the overlay |
| **TLS certs** | cert-manager + Let's Encrypt; or each cloud's certificate manager |
| **Secrets** | ExternalSecrets / SecretsStore CSI pointing at AWS Secrets Manager / Azure Key Vault / GCP Secret Manager |
| **Workload Identity / IRSA / Pod Identity** | Per-cloud, attaches the pod to a managed identity that the SDK picks up via `DefaultAzureCredential`, the AWS SDK default chain, or GCP ADC |

## Apply (smoke test on any cluster)

```sh
# Build the images first (see middleware/*/Dockerfile)
docker build -f middleware/DataMgmt-Service/Dockerfile -t rhc-datamgmt:dev .
docker build -f middleware/RAGMgmt-Service/Dockerfile  -t rhc-ragmgmt:dev .

# Load into local cluster (kind / minikube / k3d / Docker Desktop k8s)
kind load docker-image rhc-datamgmt:dev rhc-ragmgmt:dev

# Apply
kubectl apply -k DevOps/Cloud/k8s/base

# Verify
kubectl -n rhc-rag get all,ingress
kubectl -n rhc-rag rollout status deploy/datamgmt
kubectl -n rhc-rag rollout status deploy/ragmgmt
```

> **Note:** the example Secret manifests ship with `PLACEHOLDER_DO_NOT_COMMIT`. Replace via overlay, ExternalSecrets, or a sealed-secret tool before applying to anything beyond a throwaway cluster.

## Recipe per cloud

### AWS EKS

- Image registry: ECR. Build with `--build-arg SECRETS_PROVIDER=aws`, push to `<acct>.dkr.ecr.<region>.amazonaws.com/rhc-{datamgmt,ragmgmt}:<tag>`.
- Postgres: RDS for PostgreSQL with `pgvector` extension enabled.
- Secrets: AWS Secrets Manager + ExternalSecrets controller; ServiceAccount with IRSA so `boto3` picks up role creds.
- Ingress: ALB Ingress Controller. Add annotations `alb.ingress.kubernetes.io/scheme: internet-facing`, `target-type: ip`, `certificate-arn: <acm-cert-arn>`.
- Airflow: MWAA, mount `middleware/Regulated-Healthcare-DAGS/` to an S3 bucket the MWAA env reads.

### Azure AKS

- Image registry: ACR. Build with `--build-arg SECRETS_PROVIDER=azure`.
- Postgres: Azure Database for PostgreSQL Flexible Server, install `pgvector` extension.
- Secrets: AKV CSI driver; pod uses Workload Identity, `DefaultAzureCredential` resolves at runtime.
- Ingress: AGIC; annotations `appgw.ingress.kubernetes.io/ssl-redirect: "true"`.
- Airflow: Astronomer on AKS, or Cloud Composer (cross-cloud).

### GCP GKE

- Image registry: Artifact Registry. Build with `--build-arg SECRETS_PROVIDER=gcp`.
- Postgres: AlloyDB for PostgreSQL (pgvector built in) or Cloud SQL with `pgvector` extension.
- Secrets: Secret Manager; pod uses Workload Identity, ADC resolves at runtime.
- Ingress: GCE Ingress + ManagedCertificate.
- Airflow: Cloud Composer; mount DAGs from a GCS bucket the Composer env points at.

## Adding a per-cloud overlay (suggested layout)

```
DevOps/Cloud/k8s/
├── base/
└── overlays/
    ├── aws/
    │   ├── kustomization.yaml         # bases: ../../base; namespace prefix; image refs
    │   ├── ingress-alb-patch.yaml
    │   └── externalsecrets.yaml
    ├── azure/
    │   ├── kustomization.yaml
    │   ├── ingress-agic-patch.yaml
    │   └── secret-csi.yaml
    └── gcp/
        ├── kustomization.yaml
        ├── ingress-gce-patch.yaml
        └── managedcertificate.yaml
```

Overlays apply with `kubectl apply -k DevOps/Cloud/k8s/overlays/aws` etc.
