// Deletes the demouser account and all related data from the production DB.
// Run from: C:\Users\gkjuw\AppData\Local\Programs\ogenti\resources\backend
// with DATABASE_URL pointing at the production ogenti.db

const { PrismaClient } = require('@prisma/client');
const prisma = new PrismaClient();

async function main() {
  // Find the demouser
  const demoUser = await prisma.user.findFirst({
    where: { OR: [{ username: 'demouser' }, { email: 'user@ogenti.app' }] },
  });

  if (!demoUser) {
    console.log('demouser not found — nothing to delete.');
    await prisma.$disconnect();
    return;
  }

  console.log(`Found demouser: id=${demoUser.id} username=${demoUser.username} email=${demoUser.email}`);

  // 1. Get all purchaseIds for demouser
  const purchases = await prisma.purchase.findMany({
    where: { userId: demoUser.id },
    select: { id: true, agentId: true },
  });
  console.log(`  Purchases: ${purchases.length}`);
  const purchaseIds = purchases.map(p => p.id);

  // 2. Delete agent profiles for those purchases
  if (purchaseIds.length > 0) {
    const del1 = await prisma.agentProfile.deleteMany({ where: { purchaseId: { in: purchaseIds } } });
    console.log(`  Deleted ${del1.count} AgentProfiles`);

    // 3. Delete purchases
    const del2 = await prisma.purchase.deleteMany({ where: { id: { in: purchaseIds } } });
    console.log(`  Deleted ${del2.count} Purchases`);
  }

  // 4. Delete community votes by demouser
  const del3 = await prisma.communityVote.deleteMany({ where: { userId: demoUser.id } });
  console.log(`  Deleted ${del3.count} CommunityVotes`);

  // 5. Delete community posts by demouser (and their comments/votes)
  const posts = await prisma.communityPost.findMany({ where: { authorId: demoUser.id }, select: { id: true } });
  if (posts.length > 0) {
    await prisma.communityVote.deleteMany({ where: { postId: { in: posts.map(p => p.id) } } });
    await prisma.communityComment.deleteMany({ where: { postId: { in: posts.map(p => p.id) } } });
    const del4 = await prisma.communityPost.deleteMany({ where: { authorId: demoUser.id } });
    console.log(`  Deleted ${del4.count} CommunityPosts`);
  }

  // 6. Delete reviews by demouser
  const del5 = await prisma.agentReview.deleteMany({ where: { userId: demoUser.id } });
  console.log(`  Deleted ${del5.count} AgentReviews`);

  // 7. Delete notifications
  const del6 = await prisma.notification.deleteMany({ where: { userId: demoUser.id } });
  console.log(`  Deleted ${del6.count} Notifications`);

  // 8. Delete user settings
  await prisma.userSettings.deleteMany({ where: { userId: demoUser.id } });

  // 9. Delete credit ledger entries
  const del7 = await prisma.creditLedger.deleteMany({ where: { userId: demoUser.id } });
  console.log(`  Deleted ${del7.count} CreditLedger entries`);

  // 10. Delete the user itself
  await prisma.user.delete({ where: { id: demoUser.id } });
  console.log(`  DELETED user: ${demoUser.username} (${demoUser.email})`);

  console.log('\ndemouser cleanup complete.');
  await prisma.$disconnect();
}

main().catch(e => { console.error(e); process.exit(1); });
