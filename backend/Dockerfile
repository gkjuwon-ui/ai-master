# ogenti Backend — Railway Dockerfile
# Build context: REPO ROOT (root railway.toml -> dockerfilePath = "backend/Dockerfile")
# Cache bust: v5

# ── Stage 1: builder ─────────────────────────────────────────────
FROM node:20-alpine AS builder

RUN apk add --no-cache python3 make g++

# WORKDIR = /app (repo root level in container)
WORKDIR /app

# Copy ONLY what's needed - paths relative to REPO ROOT build context
COPY tsconfig.base.json ./
COPY shared/ ./shared/
COPY backend/package.json ./backend/package.json
COPY backend/prisma/ ./backend/prisma/
COPY backend/src/ ./backend/src/
COPY backend/tsconfig.json ./backend/tsconfig.json

# Install deps inside /app/backend
WORKDIR /app/backend
RUN npm install --no-package-lock

# Ensure PostgreSQL provider
RUN sed -i 's/provider = "sqlite"/provider = "postgresql"/g' prisma/schema.prisma || true

# Generate Prisma client
RUN npx prisma generate

# Compile TypeScript
RUN ./node_modules/.bin/tsc --project tsconfig.json

# ── Stage 2: runner ──────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

RUN apk add --no-cache tini wget
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 ogenti

COPY --from=builder /app/backend/node_modules ./node_modules
COPY --from=builder /app/backend/dist ./dist
COPY --from=builder /app/backend/prisma ./prisma
COPY --from=builder /app/backend/package.json ./

# Inline entrypoint — no COPY from build context needed
RUN printf '#!/bin/sh\nset -e\necho "Applying DB schema..."\nnpx prisma db push --skip-generate 2>&1 || npx prisma migrate deploy 2>&1 || { echo "DB schema failed"; exit 1; }\necho "Starting server..."\nexec node dist/server.js\n' > entrypoint.sh \
 && chmod +x entrypoint.sh

USER ogenti

EXPOSE 4000
ENV NODE_ENV=production
ENV PORT=4000

ENTRYPOINT ["tini", "--"]
CMD ["./entrypoint.sh"]
