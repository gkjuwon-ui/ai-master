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
  debugLog(`PORT=${env.PORT}, DATABASE_URL=${env.DATABASE_URL}`);

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

    // All known migrations in chronological order
    const allMigrations = [
      '20260206053336_init',
      '20260207000000_add_subscriptions',
      '20260207100000_add_premium_trial_and_apex',
      '20260212054019_add_execution_metric',
      '20260215000000_add_credits_community',
      '20260216000000_add_purchase_persona',
      '20260217000000_add_agentid_to_community_vote',
      '20260218000000_add_agentids_fix_constraints',
      '20260219000000_add_daily_idle_token_limit',
      '20260220000000_add_feed_algorithm',
      '20260220100000_reset_community_data',
    ];
    // Baseline migrations (already in DB before migration history existed)
    // The last migration should NOT be baselined — it needs to actually run
    const baselineMigrations = allMigrations.slice(0, -1);
    
    let deployed = false;
    try {
      execSync(`${prismaCmd} migrate deploy`, migrateOpts);
      debugLog('Prisma migrations completed');
      deployed = true;
    } catch (migrateErr) {
      const errMsg = migrateErr.stderr ? migrateErr.stderr.toString() : migrateErr.message;
      debugLog(`Migration issue: ${errMsg}`);
      
      // If schema is not empty (P3005), resolve all known migrations as baseline
      if (errMsg.includes('P3005')) {
        debugLog('Database already has tables but no migration history. Resolving baselines...');
        for (const mig of baselineMigrations) {
          try {
            execSync(`${prismaCmd} migrate resolve --applied ${mig}`, migrateOpts);
            debugLog(`  Resolved: ${mig}`);
          } catch (resolveErr) {
            debugLog(`  Resolve ${mig}: ${resolveErr.message}`);
          }
        }
        // Re-run deploy to apply any remaining migrations
        try {
          execSync(`${prismaCmd} migrate deploy`, migrateOpts);
          debugLog('Prisma migrations completed (after baseline)');
          deployed = true;
        } catch (retryErr) {
          debugLog(`Migration retry failed: ${retryErr.message}`);
        }
      }
    }

    // Fallback: if migrate deploy failed, try db push as last resort
    if (!deployed) {
      debugLog('Falling back to prisma db push...');
      try {
        execSync(`${prismaCmd} db push --accept-data-loss`, migrateOpts);
        debugLog('Database schema pushed successfully');
      } catch (pushErr) {
        debugLog(`db push failed: ${pushErr.message}`);
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
