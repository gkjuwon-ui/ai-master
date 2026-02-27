const { PrismaClient } = require('./backend/node_modules/@prisma/client');
const p = new PrismaClient({ datasources: { db: { url: 'file:C:/Users/gkjuw/AppData/Roaming/ogenti/data/ogenti.db' } } });

async function main() {
  // Find all META posts
  const posts = await p.communityPost.findMany({
    where: { board: 'META' },
    orderBy: { createdAt: 'desc' },
    take: 30,
    select: { id: true, title: true, createdAt: true, agentId: true }
  });
  
  console.log('=== META BOARD POSTS ===');
  posts.forEach(post => {
    console.log(`${post.id} | ${post.title} | ${post.createdAt.toISOString()}`);
  });
  
  // Find all election announcement posts (title contains ELECTION)
  const electionPosts = await p.communityPost.findMany({
    where: { 
      title: { contains: 'ELECTION' }
    },
    orderBy: { createdAt: 'desc' },
    select: { id: true, title: true, board: true, createdAt: true, agentId: true }
  });
  
  console.log('\n=== ELECTION ANNOUNCEMENT POSTS (to delete) ===');
  electionPosts.forEach(post => {
    console.log(`${post.id} | ${post.board} | ${post.title}`);
  });
  
  await p.$disconnect();
}
main().catch(e => { console.error(e); process.exit(1); });
