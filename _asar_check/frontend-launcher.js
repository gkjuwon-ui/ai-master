/**
 * Frontend Launcher — loads Next.js standalone server in-process (production)
 * or spawns npx next start in development mode.
 */

const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

let frontendProcess = null;
let frontendStarted = false;

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
  const line = `[${timestamp}] [Frontend] ${msg}`;
  console.log(line);
  try { fs.appendFileSync(getLogPath(), line + '\n'); } catch {}
}

/**
 * Launch the Next.js standalone server.
 */
function launchFrontend(frontendPath, env, isDev) {
  return new Promise((resolve) => {
    try {
      if (isDev) {
        launchFrontendDev(frontendPath, env, resolve);
      } else {
        launchFrontendInProcess(frontendPath, env, resolve);
      }
    } catch (err) {
      debugLog(`Launch error: ${err.message}`);
      resolve(null);
    }
  });
}

/**
 * Production: spawn Next.js standalone server as a separate process.
 */
function launchFrontendInProcess(frontendPath, env, resolve) {
  const serverScript = path.join(frontendPath, 'standalone', 'frontend', 'server.js');

  debugLog(`Launching standalone server: ${serverScript}`);

  if (!fs.existsSync(serverScript)) {
    debugLog(`server.js not found: ${serverScript}`);
    resolve(null);
    return;
  }

  // Use Electron itself as Node.js via ELECTRON_RUN_AS_NODE=1
  // This is the most reliable way — no dependency on system node.exe
  const nodeExec = process.execPath;

  const cwd = path.dirname(serverScript);
  debugLog(`Working directory: ${cwd}`);
  debugLog(`Node executable: ${nodeExec}`);
  debugLog(`Environment: PORT=${env.PORT}, HOSTNAME=0.0.0.0`);

  // Spawn Next.js as separate process for better error handling
  frontendProcess = spawn(nodeExec, [serverScript], {
    cwd,
    env: {
      ...process.env,
      ELECTRON_RUN_AS_NODE: '1',
      PORT: env.PORT || '3000',
      HOSTNAME: '127.0.0.1',
      NEXT_PUBLIC_API_URL: env.NEXT_PUBLIC_API_URL || '',
      NEXT_PUBLIC_WS_URL: env.NEXT_PUBLIC_WS_URL || '',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  debugLog(`Frontend process PID: ${frontendProcess.pid}`);

  frontendProcess.stdout?.on('data', (d) => {
    const msg = d.toString().trim();
    if (msg) debugLog(msg);
  });
  
  frontendProcess.stderr?.on('data', (d) => {
    const msg = d.toString().trim();
    if (msg) debugLog(`ERR: ${msg}`);
  });
  
  frontendProcess.on('error', (err) => {
    debugLog(`Process error: ${err.message} ${err.stack || ''}`);
  });
  
  frontendProcess.on('exit', (code, signal) => {
    debugLog(`Frontend exited with code ${code}, signal ${signal}`);
    frontendProcess = null;
  });

  // Give it a moment to start
  setTimeout(() => {
    if (frontendProcess && !frontendProcess.killed) {
      frontendStarted = true;
      debugLog('Frontend process spawned successfully');
      resolve(frontendProcess);
    } else {
      debugLog('Frontend process failed to start');
      resolve(null);
    }
  }, 500);
}

/**
 * Development: spawn npx next start.
 */
function launchFrontendDev(frontendPath, env, resolve) {
  const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';
  frontendProcess = spawn(npx, ['next', 'start', '-p', env.PORT || '3000'], {
    cwd: frontendPath,
    env: { ...process.env, ...env },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  frontendProcess.stdout?.on('data', (d) => debugLog(d.toString().trim()));
  frontendProcess.stderr?.on('data', (d) => debugLog(`ERR: ${d.toString().trim()}`));
  frontendProcess.on('error', (err) => debugLog(`Process error: ${err.message}`));
  frontendProcess.on('exit', (code) => { debugLog(`Exited with code ${code}`); frontendProcess = null; });

  setTimeout(() => resolve(frontendProcess), 1000);
}

/**
 * Stop the frontend process.
 */
async function stopFrontend(proc) {
  frontendStarted = false;
  const p = proc || frontendProcess;
  if (!p) return;

  return new Promise((resolve) => {
    try {
      const kill = require('tree-kill');
      kill(p.pid, 'SIGTERM', (err) => {
        if (err) { try { p.kill('SIGKILL'); } catch {} }
        frontendProcess = null;
        resolve();
      });
    } catch {
      try { p.kill(); } catch {}
      frontendProcess = null;
      resolve();
    }
  });
}

module.exports = { launchFrontend, stopFrontend };
