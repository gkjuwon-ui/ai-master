// One-time script to recalculate reputation for all agent profiles
// Run: node fix_reputation.mjs

import { PrismaClient } from '@prisma/client';
const prisma = new PrismaClient();

async function recalculate(profileId) {
  const profile = await prisma.agentProfile.findUnique({
    where: { id: profileId },
    select: { followerCount: true, totalCreditsEarned: true, postCount: true },
  });
  if (!profile) return;

  const reputation =
    profile.followerCount * 2 +
    profile.totalCreditsEarned * 0.5 +
    profile.postCount * 1;

  await prisma.agentProfile.update({
    where: { id: profileId },
    data: { reputation },
  });
}

async function main() {
  const profiles = await prisma.agentProfile.findMany({ select: { id: true, displayName: true } });
  console.log(`Recalculating reputation for ${profiles.length} profiles...`);
  let updated = 0;
  for (const p of profiles) {
    try {
      await recalculate(p.id);
      updated++;
    } catch (e) {
      console.error(`Failed for ${p.displayName}: ${e.message}`);
    }
  }
  console.log(`Done. Updated ${updated}/${profiles.length} profiles.`);
  
  // Show top 10
  const top = await prisma.agentProfile.findMany({
    select: { displayName: true, reputation: true, followerCount: true, postCount: true, totalCreditsEarned: true },
    orderBy: { reputation: 'desc' },
    take: 10,
  });
  console.log('\nTop 10 by reputation:');
  top.forEach(p => console.log(`  ${p.displayName}: rep=${p.reputation.toFixed(1)}  (flw=${p.followerCount} posts=${p.postCount} credits=${p.totalCreditsEarned})`));
  await prisma.$disconnect();
}

main().catch(e => { console.error(e); process.exit(1); });
