import { PrismaClient } from '@prisma/client';
const p = new PrismaClient();
try {
  const agents = await p.agent.count();
  const users = await p.user.count();
  console.log('Agents:', agents);
  console.log('Users:', users);
  const tables = await p['']("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('OwnerChat','OwnerChatMessage','OwnerChatParticipant','AgentOwnerMemory') ORDER BY name");
  console.log('OwnerChat tables:', tables.map(t => t.name));
  const oc = await p.ownerChat.count();
  console.log('OwnerChat rows:', oc);
} catch(e) { console.error('ERROR:', e.message); }
await p['']();
