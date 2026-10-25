# CertiGuard frontend: build the React SPA, serve it with non-root Nginx.
#
# Build context is ./frontend:
#   docker compose build frontend
#
# Only public, build-time Vite values may be passed as build args. Vite inlines
# them into the served JavaScript bundle, so NEVER pass backend secrets
# (CLERK_SECRET_KEY, DATABASE_URL, etc.) here.

FROM node:20-alpine AS build
WORKDIR /app

# Public Clerk publishable key (pk_test_/pk_live_). Safe to expose.
ARG VITE_CLERK_PUBLISHABLE_KEY=""
# Empty = same-origin "/api/..." requests through Nginx (the supported setup).
ARG VITE_API_BASE_URL=""

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

RUN if [ -z "$VITE_CLERK_PUBLISHABLE_KEY" ]; then \
        echo "WARNING: VITE_CLERK_PUBLISHABLE_KEY is empty; sign-in will be unavailable." >&2; \
    fi; \
    VITE_CLERK_PUBLISHABLE_KEY="$VITE_CLERK_PUBLISHABLE_KEY" \
    VITE_API_BASE_URL="$VITE_API_BASE_URL" \
    npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/ || exit 1
