// Default (development) environment. Replaced by environment.production.ts at build
// time when --configuration=production is used (see angular.json fileReplacements).
//
// Anything that varies per deployment target (k8s ingress vs local dev, cloud A vs B)
// belongs here, NOT in component code. Empty values mean "feature off / link hidden".
export const environment = {
  production: false,
  airflowUiBase: 'http://localhost:8080',
};
