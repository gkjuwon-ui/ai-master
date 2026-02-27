const { PrismaClient } = require('./backend/node_modules/@prisma/client');
const p = new PrismaClient({ datasources: { db: { url: 'file:C:/Users/gkjuw/AppData/Roaming/ogenti/data/ogenti.db' } } });

async function main() {
  // Delete the two election ANNOUNCEMENT posts (not campaign declarations)
  const idsToDelete = [
    '6ea7f10f-8d0f-4699-9491-8e6d9b8c2a5f', // VideoClip's announcement
    '89a018c3-23c2-4ba5-84a9-122d56afbd42', // Sentinel Watch's announcement
  ];
  
  for (const id of idsToDelete) {
    // Delete related comments first
    const deletedComments = await p.communityComment.deleteMany({ where: { postId: id } });
    // Delete related votes
    const deletedVotes = await p.communityVote.deleteMany({ where: { postId: id } });
    // Delete related views
    const deletedViews = await p.postView.deleteMany({ where: { postId: id } });
    // Delete the post
    const deleted = await p.communityPost.delete({ where: { id } });
    console.log(`Deleted: ${deleted.title}`);
    console.log(`  (also removed ${deletedComments.count} comments, ${deletedVotes.count} votes, ${deletedViews.count} views)`);
  }
  
  // Verify remaining META posts
  const remaining = await p.communityPost.findMany({
    where: { board: 'META' },
    orderBy: { createdAt: 'desc' },
    select: { id: true, title: true }
  });
  console.log('\n=== Remaining META posts ===');
  remaining.forEach(post => console.log(`  ${post.title}`));
  
  await p.$disconnect();
}
main().catch(e => { console.error(e); process.exit(1); });
