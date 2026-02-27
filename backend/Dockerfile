# ogenti Backend Dockerfile - Multi-stage build for production

# Stage 1: Install prod-only dependencies
FROM node:20-alpine AS deps
WORKDIR /app

COPY backend/package.json ./backend/
COPY shared/ ./shared/

WORKDIR /app/backend
RUN npm install --omit=dev --no-package-lock

# Stage 2: Build TypeScript (needs devDependencies like typescript, prisma)
FROM node:20-alpine AS builder
WORKDIR /app

COPY backend/package.json ./backend/
COPY shared/ ./shared/
COPY tsconfig.base.json ./

WORKDIR /app/backend
RUN npm install --no-package-lock

COPY backend/ ./backend/

# Switch from SQLite to PostgreSQL for Railway deployment
RUN sed -i 's/provider = "sqlite"/provider = "postgresql"/g' prisma/schema.prisma

# Generate Prisma client (with PostgreSQL provider)
RUN npx prisma generate

# Build TypeScript
RUN ./node_modules/.bin/tsc --project tsconfig.json

# Stage 3: Production image
FROM node:20-alpine AS runner
WORKDIR /app

RUN apk add --no-cache wget tini
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 ogenti

COPY --from=deps /app/backend/node_modules ./node_modules
COPY --from=builder /app/backend/dist ./dist
COPY --from=builder /app/backend/prisma ./prisma
COPY --from=builder /app/backend/package.json ./

COPY backend/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

USER ogenti

EXPOSE 4000

ENV NODE_ENV=production
ENV PORT=4000

ENTRYPOINT ["tini", "--"]
CMD ["./entrypoint.sh"]
