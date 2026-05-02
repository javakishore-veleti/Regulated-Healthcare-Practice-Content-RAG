# Admin portal — multi-stage Dockerfile.
# Stage 1: node:20-alpine builds the Angular production bundle.
# Stage 2: nginxinc/nginx-unprivileged serves the static files as non-root.
#
# Build context is this directory:
#   docker build -t rhc-admin:dev portals/admin
#
# The unprivileged nginx image listens on 8080 (not 80) and runs as uid 101.

# ─── Stage 1: build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps from package-lock.json (deterministic).
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and build the production bundle. Angular 17+ emits to
# `dist/<project-name>/browser/` by default.
COPY . ./
RUN npm run build -- --configuration=production

# ─── Stage 2: serve ───────────────────────────────────────────────────────────
FROM nginxinc/nginx-unprivileged:1.27-alpine

# Bring in the SPA bundle. The `browser/` subdir is where Angular's
# application builder puts the client artefacts; we drop them at the
# nginx html root.
COPY --from=builder --chown=nginx:nginx /app/dist/admin/browser /usr/share/nginx/html

# Replace the default nginx config with the SPA-friendly one.
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:8080/healthz || exit 1
