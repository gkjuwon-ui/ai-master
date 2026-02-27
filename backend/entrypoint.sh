#!/bin/sh
set -e

echo "Applying database schema..."
npx prisma db push --skip-generate 2>&1 || {
  echo "WARNING: prisma db push failed, trying migrate deploy..."
  npx prisma migrate deploy 2>&1 || {
    echo "ERROR: Database schema could not be applied."
    exit 1
  }
}
echo "Database schema applied successfully."

echo "Seeding database (if needed)..."
npx prisma db seed 2>/dev/null || true

echo "Starting backend server..."
exec node dist/server.js
