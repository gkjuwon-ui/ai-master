const { PrismaClient } = require('@prisma/client');
const path = require('path');

process.env.DATABASE_URL = 'file:C:/Users/gkjuw/AppData/Roaming/ogenti/data/ogenti.db';

const prisma = new PrismaClient();

async function main() {
  const result = await prisma.agentProfile.updateMany({
    where: { NOT: { selfPromptHash: '' } },
    data: { selfPromptHash: '' },
  });
  console.log('Reset:', result.count, 'agents');
}

main().then(() => prisma.$disconnect()).catch(e => { console.error(e); prisma.$disconnect(); process.exit(1); });
