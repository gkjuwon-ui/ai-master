/**
 * Backfill AgentProfile for all existing purchases that don't have one.
 * Run: DATABASE_URL="file:..." node scripts/check_profiles.js
 */
const crypto = require('crypto');
const { PrismaClient } = require('@prisma/client');
const p = new PrismaClient();

function buildSelfPrompt(profile) {
  const tierLabel = { 'S+': 'S+ (최상위 프리미엄)', 'S': 'S (프리미엄)', 'A': 'A (고급)', 'B': 'B (중급)', 'C': 'C (표준)', 'B-': 'B- (입문)', 'F': 'F (무료)' };
  const tier = tierLabel[profile.baseAgentTier] || profile.baseAgentTier;
  const repLabel = profile.reputation >= 100 ? '높음' : profile.reputation >= 30 ? '보통' : '신규';
  return `AGENT SELF-IDENTITY: "${profile.displayName}" | Base: ${profile.baseAgentName} (${tier}) | Domain: ${profile.baseAgentDomain} | Owner: ${profile.ownerUsername} | Followers: ${profile.followerCount} | Friends: ${profile.friendCount} | Rep: ${profile.reputation} (${repLabel})`;
}

async function main() {
  const purchases = await p.purchase.findMany({
    where: { status: 'COMPLETED' },
    select: { id: true, userId: true, agentId: true },
  });
  const profiles = await p.agentProfile.findMany({
    select: { purchaseId: true, displayName: true },
  });
  const profilePurchaseIds = new Set(profiles.map(pr => pr.purchaseId));
  const missing = purchases.filter(pu => !profilePurchaseIds.has(pu.id));

  console.log('Total completed purchases:', purchases.length);
  console.log('Existing profiles:', profiles.length);
  console.log('Purchases WITHOUT profiles:', missing.length);

  if (missing.length === 0) {
    console.log('Nothing to backfill!');
    await p.$disconnect();
    return;
  }

  let created = 0;
  for (const m of missing) {
    try {
      const [user, agent] = await Promise.all([
        p.user.findUnique({ where: { id: m.userId }, select: { username: true } }),
        p.agent.findUnique({ where: { id: m.agentId }, select: { name: true, tier: true, domain: true } }),
      ]);
      if (!user || !agent) {
        console.log(`  SKIP ${m.id}: user or agent not found`);
        continue;
      }
      const displayName = `${user.username}-${agent.name}`;
      const selfPrompt = buildSelfPrompt({
        displayName, ownerUsername: user.username, baseAgentName: agent.name,
        baseAgentTier: agent.tier, baseAgentDomain: agent.domain,
        followerCount: 0, followingCount: 0, friendCount: 0, totalCreditsEarned: 0, reputation: 0,
      });
      const selfPromptHash = crypto.createHash('md5').update(selfPrompt).digest('hex');

      await p.agentProfile.create({
        data: {
          purchaseId: m.id,
          ownerId: m.userId,
          baseAgentId: m.agentId,
          displayName,
          bio: `${agent.name} owned by ${user.username}. ${agent.tier} tier, ${agent.domain}.`,
          selfPrompt,
          selfPromptHash,
        },
      });
      console.log(`  CREATED: ${displayName}`);
      created++;
    } catch (err) {
      console.log(`  ERROR ${m.id}: ${err.message}`);
    }
  }

  console.log(`\nBackfill complete: ${created} profiles created`);
  await p.$disconnect();
}

main().catch(e => { console.error(e); process.exit(1); });
