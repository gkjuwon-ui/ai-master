const { PrismaClient } = require('@prisma/client');
const path = require('path');

async function fix(dbPath, label) {
  const absPath = path.resolve(dbPath).replace(/\\/g, '/');
  const url = `file:${absPath}`;
  console.log(`Connecting to: ${url}`);
  const p = new PrismaClient({ datasources: { db: { url } } });
  try {
    const subs = await p.subscription.findMany({
      where: { status: { in: ['ACTIVE', 'CANCELLED'] } },
      orderBy: { createdAt: 'desc' },
      take: 10,
    });
    console.log(`\n=== ${label} — ${subs.length} active/cancelled subs ===`);
    for (const s of subs) {
      console.log(`  id=${s.id} tier=${s.tier} status=${s.status} price=${s.priceUsd} daily=${s.dailyCredits} end=${s.currentPeriodEnd}`);
    }

    if (subs.length > 0) {
      const result = await p.subscription.updateMany({
        where: { status: { in: ['ACTIVE', 'CANCELLED'] } },
        data: { status: 'EXPIRED' },
      });
      console.log(`  -> Expired ${result.count} subscriptions`);
    } else {
      console.log('  -> No subscriptions to expire');
    }
  } finally {
    await p.$disconnect();
  }
}

(async () => {
  const base = 'c:/Users/gkjuw/Downloads/ai_master';
  await fix(`${base}/backend/prisma/dev.db`, 'DEV DB');
  await fix(`${base}/dist_v2/win-unpacked/resources/backend/prisma/dev.db`, 'PROD DB');
  console.log('\nDone.');
})();
