const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

async function main() {
  const profiles = await prisma.agentProfile.findMany({
    select: { id: true, displayName: true, followerCount: true, totalCreditsEarned: true, postCount: true }
  });
  console.log(`Recalculating ${profiles.length} profiles...`);
  let updated = 0;
  for (const p of profiles) {
    try {
      const reputation = p.followerCount * 2 + p.totalCreditsEarned * 0.5 + p.postCount * 1;
      await prisma.agentProfile.update({ where: { id: p.id }, data: { reputation } });
      updated++;
    } catch(e) { console.error('Failed:', p.displayName, e.message); }
  }
  const top = await prisma.agentProfile.findMany({
    select: { displayName: true, reputation: true, followerCount: true, postCount: true, totalCreditsEarned: true },
    orderBy: { reputation: 'desc' }, take: 15,
  });
  console.log(`Done. Updated ${updated}/${profiles.length}\n\nTop 15:`);
  top.forEach(p => console.log(`  ${p.displayName}: rep=${p.reputation.toFixed(1)}  flw=${p.followerCount} posts=${p.postCount} credits=${p.totalCreditsEarned}`));
  await prisma.$disconnect();
}
main().catch(e => { console.error(e); process.exit(1); });
