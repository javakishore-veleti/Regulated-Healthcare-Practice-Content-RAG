// Production environment. The admin portal is a static SPA served by ingress / CDN
// in cloud k8s deployments — values here MUST be set per environment via the
// deployment pipeline (envsubst on built artifacts, or a runtime /api/config fetch).
// Empty defaults render no link rather than a broken localhost link.
export const environment = {
  production: true,
  airflowUiBase: '',
};
