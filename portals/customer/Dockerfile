# Customer portal — multi-stage Dockerfile. See portals/admin/Dockerfile for
# the rationale; this one only differs in the dist project name.
#
# Build context:
#   docker build -t rhc-customer:dev portals/customer

FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . ./
RUN npm run build -- --configuration=production

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=builder --chown=nginx:nginx /app/dist/customer/browser /usr/share/nginx/html
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:8080/healthz || exit 1
