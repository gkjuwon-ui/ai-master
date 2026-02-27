# ogenti Backend — Railway Dockerfile
# Build context = backend/ directory (Railway Root Directory: ./backend)

# ── Stage 1: builder ─────────────────────────────────────────────
FROM node:20-alpine AS builder

RUN apk add --no-cache python3 make g++

WORKDIR /app

# package.json is at context root (= backend/)
COPY package.json ./
RUN npm install --no-package-lock

# Copy all backend source files
COPY . .

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

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/package.json ./
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

USER ogenti

EXPOSE 4000
ENV NODE_ENV=production
ENV PORT=4000

ENTRYPOINT ["tini", "--"]
CMD ["./entrypoint.sh"]
