# ?�?�?� ogenti Backend ?�?�?� Dockerfile ?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�
# Multi-stage build for production Node.js/Express backend

# Stage 1: Install dependencies
FROM node:20-alpine AS deps
WORKDIR /app

COPY backend/package.json backend/package-lock.json* ./backend/
COPY shared/ ./shared/
COPY package.json ./

WORKDIR /app/backend
RUN npm ci --omit=dev 2>/dev/null || npm install --omit=dev

# Build shared types first
WORKDIR /app/shared
RUN if [ -f package.json ]; then npm ci --omit=dev 2>/dev/null || true; fi

WORKDIR /app/backend

# Stage 2: Build TypeScript
FROM node:20-alpine AS builder
WORKDIR /app

COPY --from=deps /app/backend/node_modules ./backend/node_modules
COPY backend/ ./backend/
COPY shared/ ./shared/
COPY tsconfig.base.json ./

WORKDIR /app/backend

# Switch from SQLite to PostgreSQL for Railway deployment
RUN sed -i 's/provider = "sqlite"/provider = "postgresql"/g' prisma/schema.prisma

# Generate Prisma client (with PostgreSQL provider)
RUN npx prisma generate

# Build TypeScript (fail on errors — do not deploy broken builds)
RUN npx tsc --project tsconfig.json

# Stage 3: Production image
FROM node:20-alpine AS runner
WORKDIR /app

RUN apk add --no-cache wget tini
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 ogenti

COPY --from=builder /app/backend/dist ./dist
COPY --from=builder /app/backend/node_modules ./node_modules
COPY --from=builder /app/backend/prisma ./prisma
COPY --from=builder /app/backend/package.json ./

# Run migrations on startup
COPY backend/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

USER ogenti

EXPOSE 4000

ENV NODE_ENV=production
ENV PORT=4000

ENTRYPOINT ["tini", "--"]
CMD ["./entrypoint.sh"]
