/**
 * Backend launcher — loads the backend server in-process (production)
 * or spawns tsx in development mode.
 */

const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const kill = require('tree-kill');

// Parse .env file and return as object
function loadEnvFile(envPath) {
  const envContent = {};
  if (fs.existsSync(envPath)) {
    const lines = fs.readFileSync(envPath, 'utf8').split('\n');
    for (const line of lines) {
      const match = line.match(/^([^=]+)=(.*)$/);
      if (match) {
        const key = match[1].trim();
        let value = match[2].trim();
        // Remove quotes if present
        if ((value.startsWith('"') && value.endsWith('"')) || 
            (value.startsWith("'") && value.endsWith("'"))) {
          value = value.slice(1, -1);
        }
        envContent[key] = value;
      }
    }
  }
  return envContent;
}

let backendProc = null;
let backendServer = null; // for in-process mode

function getLogPath() {
  try {
    const { app } = require('electron');
    return path.join(app.getPath('userData'), 'ogenti-debug.log');
  } catch {
    return path.join(process.cwd(), 'ogenti-debug.log');
  }
}

function debugLog(msg) {
  const timestamp = new Date().toISOString();
  const line = `[${timestamp}] [Backend] ${msg}`;
  console.log(line);
  try { fs.appendFileSync(getLogPath(), line + '\n'); } catch {}
}

async function launchBackend(backendPath, env, isDev) {
  if (isDev) {
    return launchBackendDev(backendPath, env);
  }
  return launchBackendInProcess(backendPath, env);
}

/**
 * Production: load server.js directly in the Electron main process.
 * This avoids all subprocess / ELECTRON_RUN_AS_NODE issues.
 */
async function launchBackendInProcess(backendPath, env) {
  const serverJsPath = path.join(backendPath, 'dist', 'server.js');

  debugLog(`Loading in-process: ${serverJsPath}`);
  debugLog(`PORT=${env.PORT}, DATABASE_URL=file:***`);

  if (!fs.existsSync(serverJsPath)) {
    throw new Error(`Backend server.js not found: ${serverJsPath}`);
  }

  // Load .env file from backend directory and merge with provided env
  const envFilePath = path.join(backendPath, '.env');
  const fileEnv = loadEnvFile(envFilePath);
  if (Object.keys(fileEnv).length > 0) {
    debugLog(`Loaded .env from: ${envFilePath}`);
  }

  // Merge: .env file first, then explicit env — but skip empty strings from env
  // so that .env values are not overwritten by empty defaults
  const mergedEnv = { ...fileEnv };
  Object.keys(env).forEach(key => {
    if (env[key] !== '' && env[key] != null) {
      mergedEnv[key] = env[key];
    }
  });

  // Set all environment variables before requiring the server module
  // Use a scoped env object to minimize process.env pollution with secrets
  const secretKeys = ['JWT_SECRET', 'JWT_REFRESH_SECRET', 'ENCRYPTION_KEY',
                      'AGENT_RUNTIME_SECRET'];
  const envToRestore = {};
  Object.keys(mergedEnv).forEach(key => {
    envToRestore[key] = process.env[key]; // save original
    process.env[key] = mergedEnv[key];
  });

  // Use absolute paths for upload and log directories
  process.env.UPLOAD_DIR = path.join(backendPath, 'uploads');
  process.env.LOG_DIR = path.join(backendPath, 'logs');

  // Ensure directories exist
  [process.env.UPLOAD_DIR, process.env.LOG_DIR].forEach(dir => {
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  });

  // Run Prisma migrations
  debugLog('Running Prisma migrations...');
  try {
    const { execSync } = require('child_process');
    // Always use the bundled prisma via Electron's Node.js runtime.
    // Using .bin/prisma.cmd or npx can pick up wrong system Node version.
    const prismaJsPath = path.join(backendPath, 'node_modules', 'prisma', 'build', 'index.js');
    let prismaCmd;
    if (fs.existsSync(prismaJsPath)) {
      // Use Electron as Node.js via ELECTRON_RUN_AS_NODE — consistent runtime
      prismaCmd = `"${process.execPath}" "${prismaJsPath}"`;
      debugLog(`Using bundled prisma: ${prismaJsPath} (via ${process.execPath})`);
    } else {
      prismaCmd = 'npx prisma';
      debugLog('WARNING: Using npx prisma fallback (may pick up wrong version)');
    }
    const migrateEnv = {
      ...process.env,
      DATABASE_URL: process.env.DATABASE_URL,
      ELECTRON_RUN_AS_NODE: '1',  // Make Electron behave as plain Node.js
    };
    const migrateOpts = { cwd: backendPath, env: migrateEnv, stdio: 'pipe', timeout: 30000 };

    let deployed = false;

    // Primary: use db push (no migration files needed, safe for SQLite)
    debugLog('Applying schema with prisma db push...');
    try {
      execSync(`${prismaCmd} db push`, migrateOpts);
      debugLog('Database schema pushed successfully');
      deployed = true;
    } catch (pushErr) {
      debugLog(`db push failed: ${pushErr.message}`);
    }

    if (!deployed) {
      debugLog('Falling back to raw SQL...');
      try {
        // Final fallback: use Prisma Client to create missing tables via raw SQL
        debugLog('Attempting raw SQL schema sync as final fallback...');
        try {
          const { PrismaClient } = require(path.join(backendPath, 'node_modules', '@prisma', 'client'));
          const prisma = new PrismaClient({ datasources: { db: { url: process.env.DATABASE_URL } } });
          // Check existing tables
          const existing = await prisma.$queryRawUnsafe("SELECT name FROM sqlite_master WHERE type='table'");
          const existingNames = new Set(existing.map(t => t.name));
          debugLog(`Existing tables: ${existingNames.size}`);
          
          // Create missing tables (critical ones that may be absent)
          const missingTableSQL = [];
          if (!existingNames.has('AgentProfile')) {
            missingTableSQL.push(`CREATE TABLE IF NOT EXISTS "AgentProfile" ("id" TEXT NOT NULL PRIMARY KEY, "agentId" TEXT NOT NULL, "ownerId" TEXT NOT NULL, "purchaseId" TEXT, "displayName" TEXT NOT NULL, "bio" TEXT, "personality" TEXT NOT NULL DEFAULT 'balanced', "autonomyLevel" TEXT NOT NULL DEFAULT 'moderate', "isActive" INTEGER NOT NULL DEFAULT 1, "totalTokensUsed" INTEGER NOT NULL DEFAULT 0, "reputation" INTEGER NOT NULL DEFAULT 0, "level" INTEGER NOT NULL DEFAULT 1, "lastActiveAt" DATETIME, "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "updatedAt" DATETIME NOT NULL, CONSTRAINT "AgentProfile_agentId_fkey" FOREIGN KEY ("agentId") REFERENCES "Agent" ("id") ON DELETE CASCADE ON UPDATE CASCADE, CONSTRAINT "AgentProfile_ownerId_fkey" FOREIGN KEY ("ownerId") REFERENCES "User" ("id") ON DELETE CASCADE ON UPDATE CASCADE, CONSTRAINT "AgentProfile_purchaseId_fkey" FOREIGN KEY ("purchaseId") REFERENCES "Purchase" ("id") ON DELETE SET NULL ON UPDATE CASCADE)`);
          }
          if (!existingNames.has('AgentFollow')) {
            missingTableSQL.push(`CREATE TABLE IF NOT EXISTS "AgentFollow" ("id" TEXT NOT NULL PRIMARY KEY, "followerId" TEXT NOT NULL, "targetId" TEXT NOT NULL, "status" TEXT NOT NULL DEFAULT 'accepted', "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, CONSTRAINT "AgentFollow_followerId_fkey" FOREIGN KEY ("followerId") REFERENCES "AgentProfile" ("id") ON DELETE CASCADE ON UPDATE CASCADE, CONSTRAINT "AgentFollow_targetId_fkey" FOREIGN KEY ("targetId") REFERENCES "AgentProfile" ("id") ON DELETE CASCADE ON UPDATE CASCADE)`);
          }
          if (!existingNames.has('AgentChatRoom')) {
            missingTableSQL.push(`CREATE TABLE IF NOT EXISTS "AgentChatRoom" ("id" TEXT NOT NULL PRIMARY KEY, "name" TEXT, "type" TEXT NOT NULL DEFAULT 'dm', "createdById" TEXT, "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "updatedAt" DATETIME NOT NULL)`);
          }
          if (!existingNames.has('AgentChatMember')) {
            missingTableSQL.push(`CREATE TABLE IF NOT EXISTS "AgentChatMember" ("id" TEXT NOT NULL PRIMARY KEY, "roomId" TEXT NOT NULL, "profileId" TEXT NOT NULL, "joinedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, CONSTRAINT "AgentChatMember_roomId_fkey" FOREIGN KEY ("roomId") REFERENCES "AgentChatRoom" ("id") ON DELETE CASCADE ON UPDATE CASCADE, CONSTRAINT "AgentChatMember_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "AgentProfile" ("id") ON DELETE CASCADE ON UPDATE CASCADE)`);
          }
          if (!existingNames.has('AgentMessage')) {
            missingTableSQL.push(`CREATE TABLE IF NOT EXISTS "AgentMessage" ("id" TEXT NOT NULL PRIMARY KEY, "roomId" TEXT NOT NULL, "senderId" TEXT NOT NULL, "content" TEXT NOT NULL, "type" TEXT NOT NULL DEFAULT 'text', "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, CONSTRAINT "AgentMessage_roomId_fkey" FOREIGN KEY ("roomId") REFERENCES "AgentChatRoom" ("id") ON DELETE CASCADE ON UPDATE CASCADE, CONSTRAINT "AgentMessage_senderId_fkey" FOREIGN KEY ("senderId") REFERENCES "AgentProfile" ("id") ON DELETE CASCADE ON UPDATE CASCADE)`);
          }
          if (!existingNames.has('AgentNotification')) {
            missingTableSQL.push(`CREATE TABLE IF NOT EXISTS "AgentNotification" ("id" TEXT NOT NULL PRIMARY KEY, "profileId" TEXT NOT NULL, "type" TEXT NOT NULL, "title" TEXT NOT NULL, "message" TEXT, "data" TEXT, "isRead" INTEGER NOT NULL DEFAULT 0, "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, CONSTRAINT "AgentNotification_profileId_fkey" FOREIGN KEY ("profileId") REFERENCES "AgentProfile" ("id") ON DELETE CASCADE ON UPDATE CASCADE)`);
          }
          if (!existingNames.has('OwnerChat')) {
            missingTableSQL.push(`CREATE TABLE IF NOT EXISTS "OwnerChat" ("id" TEXT NOT NULL PRIMARY KEY, "name" TEXT, "type" TEXT NOT NULL DEFAULT 'direct', "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "updatedAt" DATETIME NOT NULL)`);
          }
          if (!existingNames.has('OwnerChatParticipant')) {
            missingTableSQL.push(`CREATE TABLE IF NOT EXISTS "OwnerChatParticipant" ("id" TEXT NOT NULL PRIMARY KEY, "chatId" TEXT NOT NULL, "agentProfileId" TEXT NOT NULL, "joinedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, CONSTRAINT "OwnerChatParticipant_chatId_fkey" FOREIGN KEY ("chatId") REFERENCES "OwnerChat" ("id") ON DELETE CASCADE ON UPDATE CASCADE, CONSTRAINT "OwnerChatParticipant_agentProfileId_fkey" FOREIGN KEY ("agentProfileId") REFERENCES "AgentProfile" ("id") ON DELETE CASCADE ON UPDATE CASCADE)`);
          }
          if (!existingNames.has('OwnerChatMessage')) {
            missingTableSQL.push(`CREATE TABLE IF NOT EXISTS "OwnerChatMessage" ("id" TEXT NOT NULL PRIMARY KEY, "chatId" TEXT NOT NULL, "senderType" TEXT NOT NULL, "senderProfileId" TEXT, "content" TEXT NOT NULL, "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, CONSTRAINT "OwnerChatMessage_chatId_fkey" FOREIGN KEY ("chatId") REFERENCES "OwnerChat" ("id") ON DELETE CASCADE ON UPDATE CASCADE, CONSTRAINT "OwnerChatMessage_senderProfileId_fkey" FOREIGN KEY ("senderProfileId") REFERENCES "AgentProfile" ("id") ON DELETE SET NULL ON UPDATE CASCADE)`);
          }
          if (!existingNames.has('AgentOwnerMemory')) {
            missingTableSQL.push(`CREATE TABLE IF NOT EXISTS "AgentOwnerMemory" ("id" TEXT NOT NULL PRIMARY KEY, "agentProfileId" TEXT NOT NULL, "category" TEXT NOT NULL DEFAULT 'general', "key" TEXT NOT NULL, "value" TEXT NOT NULL, "confidence" REAL NOT NULL DEFAULT 1.0, "source" TEXT, "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "updatedAt" DATETIME NOT NULL, CONSTRAINT "AgentOwnerMemory_agentProfileId_fkey" FOREIGN KEY ("agentProfileId") REFERENCES "AgentProfile" ("id") ON DELETE CASCADE ON UPDATE CASCADE)`);
          }
          
          for (const sql of missingTableSQL) {
            await prisma.$executeRawUnsafe(sql);
          }
          if (missingTableSQL.length > 0) {
            debugLog(`Created ${missingTableSQL.length} missing tables via raw SQL fallback`);
          } else {
            debugLog('All tables already exist');
          }
          await prisma.$disconnect();
        } catch (sqlErr) {
          debugLog(`Raw SQL fallback failed: ${sqlErr.message}`);
        }
      }
    }
  } catch (err) {
    debugLog(`Migration setup error: ${err.message}`);
  }

  try {
    const backend = require(serverJsPath);
    backendServer = backend.server;
    debugLog('Server loaded in-process successfully');
    return { inProcess: true };
  } catch (err) {
    debugLog(`ERROR: ${err.stack}`);
    throw err;
  }
}

/**
 * Development: spawn tsx to run TypeScript source directly.
 */
async function launchBackendDev(backendPath, env) {
  return new Promise((resolve, reject) => {
    const spawnEnv = { ...process.env, ...env };
    backendProc = spawn('npx', ['tsx', 'src/server.ts'], {
      cwd: backendPath,
      env: spawnEnv,
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: true,
      windowsHide: true,
    });

    backendProc.stdout?.on('data', (d) => console.log(`[Backend] ${d.toString().trim()}`));
    backendProc.stderr?.on('data', (d) => console.error(`[Backend] ${d.toString().trim()}`));
    backendProc.on('error', (err) => { debugLog(`Spawn error: ${err.message}`); reject(err); });
    backendProc.on('exit', (code) => { debugLog(`Exited with code ${code}`); backendProc = null; });

    setTimeout(() => resolve(backendProc), 1000);
  });
}

async function stopBackend() {
  // In-process mode: close the http server
  if (backendServer) {
    return new Promise((resolve) => {
      backendServer.close(() => {
        debugLog('Server closed');
        backendServer = null;
        resolve();
      });
      // Force close after 3s
      setTimeout(() => { backendServer = null; resolve(); }, 3000);
    });
  }
  // Subprocess mode
  if (backendProc && backendProc.pid) {
    return new Promise((resolve) => {
      kill(backendProc.pid, 'SIGTERM', (err) => {
        if (err) console.error('Failed to kill backend:', err);
        backendProc = null;
        resolve();
      });
    });
  }
}

module.exports = { launchBackend, stopBackend };
