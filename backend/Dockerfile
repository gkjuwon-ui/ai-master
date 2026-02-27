# ogenti Backend — production Dockerfile

# ── Stage 1: builder ─────────────────────────────────────────────
FROM node:20-alpine AS builder

# Install build deps for native modules
RUN apk add --no-cache python3 make g++

# Set working dir to PROJECT ROOT so all paths match repo structure
WORKDIR /app

# Copy everything needed
COPY tsconfig.base.json ./
COPY shared/ ./shared/
COPY backend/ ./backend/

# Install ALL deps in backend (dev included, for tsc + prisma CLI)
WORKDIR /app/backend
RUN npm install --no-package-lock

# Ensure PostgreSQL provider (schema.prisma is at /app/backend/prisma/schema.prisma)
RUN sed -i 's/provider = "sqlite"/provider = "postgresql"/g' prisma/schema.prisma || true

# Generate Prisma client
RUN npx prisma generate

# Compile TypeScript (outputs to /app/backend/dist)
RUN ./node_modules/.bin/tsc --project tsconfig.json

# ── Stage 2: runner ──────────────────────────────────────────────
FROM node:20-alpine AS runner
WORKDIR /app

RUN apk add --no-cache tini wget
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 ogenti

# Copy compiled output
COPY --from=builder /app/backend/dist ./dist
COPY --from=builder /app/backend/prisma ./prisma
COPY --from=builder /app/backend/package.json ./
# Copy full node_modules (includes prisma CLI needed in entrypoint.sh)
COPY --from=builder /app/backend/node_modules ./node_modules

COPY backend/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

USER ogenti

EXPOSE 4000
ENV NODE_ENV=production
ENV PORT=4000

ENTRYPOINT ["tini", "--"]
CMD ["./entrypoint.sh"]
