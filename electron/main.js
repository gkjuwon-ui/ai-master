/**
 * ogenti — Electron Main Process
 * Embeds backend + frontend as a local desktop application.
 */

const { app, BrowserWindow, ipcMain, Tray, Menu, dialog, shell, nativeImage, safeStorage, globalShortcut, desktopCapturer, session } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const crypto = require('crypto');
const { execSync, spawn } = require('child_process');
const Store = require('electron-store');
const { launchBackend, stopBackend } = require('./backend-launcher');
const { launchRuntime, stopRuntime } = require('./runtime-launcher');
const { launchFrontend, stopFrontend } = require('./frontend-launcher');

// ── Central Server Config ──────────────────────────────────
const CENTRAL_BACKEND_URL = process.env.CENTRAL_BACKEND_URL || 'https://api.ogenti.com';
const USE_CENTRAL_SERVER = process.env.USE_LOCAL_BACKEND !== '1';

// ── Config Store ──────────────────────────────────────────
const store = new Store({
  defaults: {
    backendPort: 4000,
    frontendPort: 3000,
    runtimePort: 5000,
    dbPath: '',
    llmProvider: '',
    llmModel: '',
    llmBaseUrl: '',
    autoLaunch: true,
    minimizeToTray: true,
    theme: 'dark',
    runtimeToken: '',
  },
});

// ── Secure Secret Storage (safeStorage) ───────────────────
// Sensitive values (API keys, JWT secrets) are encrypted via
// Electron's safeStorage API backed by the OS keychain.
const SAFE_KEYS = ['llmApiKey', 'jwtSecret', 'jwtRefreshSecret', 'agentRuntimeSecret',
                   'stripeSecretKey', 'stripeWebhookSecret', 'encryptionKey', 'smtpPass'];

function safeGet(key) {
  const raw = store.get(`_enc_${key}`);
  if (!raw) return store.get(key) || '';            // fallback: legacy plaintext
  try {
    if (safeStorage.isEncryptionAvailable()) {
      return safeStorage.decryptString(Buffer.from(raw, 'base64'));
    }
  } catch {}
  return store.get(key) || '';
}

function safeSet(key, value) {
  if (!value) return;
  if (safeStorage.isEncryptionAvailable()) {
    store.set(`_enc_${key}`, safeStorage.encryptString(value).toString('base64'));
    store.delete(key); // remove legacy plaintext
  } else {
    store.set(key, value); // fallback: plaintext (Linux without keyring)
  }
}

// ── State ─────────────────────────────────────────────────
let mainWindow = null;
let tray = null;
let backendProcess = null;
let runtimeProcess = null;
let frontendProcess = null;
let isQuitting = false;

const isDev = process.argv.includes('--dev');
const resourcesPath = isDev
  ? path.resolve(__dirname, '..')
  : process.resourcesPath;

// ── Single Instance Lock (MUST be before app.whenReady) ──
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

// Bump this version whenever the seed database (agent list, schema, etc.) changes.
// On app launch, if the stored version is lower, the old user DB is backed up
// and replaced with the fresh seed DB.
const DB_SEED_VERSION = 10; // v10: full schema sync - all 40 tables including AgentProfile, AgentFollow, AgentChatRoom, Elections, etc.

// ── .env file loader ──────────────────────────────────────
// Light dotenv parser: reads KEY=VALUE lines from a .env file
function loadEnvFile(envPath) {
  const loaded = {};
  try {
    if (!fs.existsSync(envPath)) return loaded;
    const lines = fs.readFileSync(envPath, 'utf8').split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eqIdx = trimmed.indexOf('=');
      if (eqIdx <= 0) continue;
      const key = trimmed.substring(0, eqIdx).trim();
      let value = trimmed.substring(eqIdx + 1).trim();
      // Strip surrounding quotes
      if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
        value = value.slice(1, -1);
      }
      loaded[key] = value;
    }
  } catch (err) {
    // silently ignore
  }
  return loaded;
}

// ── Helpers ───────────────────────────────────────────────
function debugLog(msg) {
  const timestamp = new Date().toISOString();
  const line = `[${timestamp}] [Main] ${msg}`;
  console.log(line);
  try {
    const logPath = path.join(app.getPath('userData'), 'ogenti-debug.log');
    fs.appendFileSync(logPath, line + '\n');
  } catch {}
}

function getBackendPath() {
  return isDev
    ? path.resolve(__dirname, '..', 'backend')
    : path.join(resourcesPath, 'backend');
}

function getFrontendPath() {
  return isDev
    ? path.resolve(__dirname, '..', 'frontend')
    : path.join(resourcesPath, 'frontend');
  // In production, standalone output is at: resourcesPath/frontend/standalone/frontend/server.js
}

function getRuntimePath() {
  return isDev
    ? path.resolve(__dirname, '..', 'agent-runtime')
    : path.join(resourcesPath, 'agent-runtime');
}

function getDBPath() {
  const userDataPath = app.getPath('userData');
  return path.join(userDataPath, 'data', 'ogenti.db');
}

function killProcessesOnPorts() {
  // Use configured ports instead of hardcoded defaults
  const ports = [store.get('backendPort') || 4000, store.get('frontendPort') || 3000, store.get('runtimePort') || 5000];
  const myPid = process.pid;
  // Only kill processes whose executable matches ogenti-managed runtimes
  const EXPECTED_PROCESSES_WIN = ['node.exe', 'python.exe', 'python3.exe', 'pythonw.exe', 'ogenti.exe'];
  const EXPECTED_PROCESSES_UNIX = ['node', 'python', 'python3'];
  debugLog(`Cleaning up processes on ports: ${ports.join(', ')} (my PID: ${myPid})`);
  
  if (process.platform === 'win32') {
    try {
      // Use netstat (universally available, no admin needed) to find PIDs
      const output = execSync('netstat -ano', { windowsHide: true, encoding: 'utf8', timeout: 5000 });
      const pidsToKill = new Set();
      
      output.split('\n').forEach(line => {
        ports.forEach(port => {
          // Match LISTENING state on our ports
          const match = line.match(new RegExp(`:\\s*${port}\\s+.*?LISTENING\\s+(\\d+)`));
          if (match) {
            const pid = parseInt(match[1]);
            if (pid && pid !== myPid && pid !== 0) {
              pidsToKill.add(pid);
            }
          }
        });
      });
      
      pidsToKill.forEach(pid => {
        try {
          // Verify that the process is one we manage before killing
          const taskInfo = execSync(`tasklist /FI "PID eq ${pid}" /FO CSV /NH`, { windowsHide: true, encoding: 'utf8', timeout: 3000 }).trim();
          const processName = (taskInfo.split(',')[0] || '').replace(/"/g, '').toLowerCase();
          // Match exact names OR any python variant (python3.13.exe, python3.12.exe, etc.)
          const isManaged = EXPECTED_PROCESSES_WIN.includes(processName) || processName.startsWith('python');
          if (isManaged) {
            execSync(`taskkill /F /PID ${pid}`, { windowsHide: true, timeout: 3000 });
            debugLog(`Killed PID ${pid} (${processName})`);
          } else {
            debugLog(`WARNING: Skipping PID ${pid} — process '${processName}' is not an ogenti-managed process`);
          }
        } catch (e) {
          debugLog(`Could not verify/kill PID ${pid}: ${e.message}`);
        }
      });
    } catch (error) {
      debugLog(`Port cleanup error: ${error.message}`);
    }
  } else {
    ports.forEach(port => {
      try {
        const pids = execSync(`lsof -ti:${port}`, { shell: true, encoding: 'utf8', timeout: 5000 }).trim().split('\n').filter(p => p && p !== String(myPid));
        pids.forEach(pidStr => {
          const pid = parseInt(pidStr);
          if (!pid) return;
          try {
            const comm = execSync(`ps -p ${pid} -o comm=`, { shell: true, encoding: 'utf8', timeout: 3000 }).trim().toLowerCase();
            if (EXPECTED_PROCESSES_UNIX.some(name => comm.includes(name))) {
              execSync(`kill -9 ${pid}`, { shell: true });
              debugLog(`Killed PID ${pid} (${comm})`);
            } else {
              debugLog(`WARNING: Skipping PID ${pid} — process '${comm}' is not an ogenti-managed process`);
            }
          } catch {}
        });
      } catch {}
    });
  }
  
  debugLog('Port cleanup completed');
}

function ensureDataDir() {
  const dataDir = path.dirname(getDBPath());
  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
  
  const dbDest = getDBPath();
  const seedDb = isDev
    ? path.resolve(__dirname, '..', 'backend', 'prisma', 'dev.db')
    : path.join(resourcesPath, 'backend', 'prisma', 'dev.db');

  const lastSeedVersion = store.get('dbSeedVersion', 0);
  const needsReseed = lastSeedVersion < DB_SEED_VERSION;

  if (fs.existsSync(seedDb) && (!fs.existsSync(dbDest) || needsReseed)) {
    // Backup old DB if it exists (preserve user data just in case)
    if (fs.existsSync(dbDest)) {
      const backupPath = dbDest + '.backup.' + Date.now();
      try {
        fs.copyFileSync(dbDest, backupPath);
        debugLog(`Backed up old database to ${backupPath}`);
      } catch (backupErr) {
        debugLog(`Could not backup old DB: ${backupErr.message}`);
      }
    }
    fs.copyFileSync(seedDb, dbDest);
    store.set('dbSeedVersion', DB_SEED_VERSION);
    debugLog(`Seed database (v${DB_SEED_VERSION}) copied to ${dbDest}`);
  } else if (fs.existsSync(dbDest)) {
    debugLog(`Using existing database at ${dbDest} (${fs.statSync(dbDest).size} bytes, seed v${lastSeedVersion})`);
  } else {
    debugLog(`WARNING: No seed database found at ${seedDb}`);
  }
}

function getIconPath() {
  const ext = process.platform === 'win32' ? 'ico' : 'png';
  const iconPath = path.join(__dirname, 'resources', `icon.${ext}`);
  if (fs.existsSync(iconPath)) return iconPath;
  return undefined;
}

// ── Window Creation ───────────────────────────────────────
function createMainWindow() {
  const backendPort = store.get('backendPort');
  const frontendPort = store.get('frontendPort');

  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: '#0a0a0f',
    icon: getIconPath(),
    frame: false,
    titleBarStyle: 'hidden',
    titleBarOverlay: process.platform === 'win32' ? {
      color: '#0a0a0f',
      symbolColor: '#ffffff',
      height: 40,
    } : undefined,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // NOTE: cache clearing is now handled in app lifecycle (awaited before loadURL)

  // Allow sandbox window capture via getDisplayMedia without picker
  try {
    mainWindow.webContents.session.setDisplayMediaRequestHandler(async (_request, callback) => {
      if (sandboxCaptureMode) {
        sandboxCaptureMode = false;
        try {
          const sources = await desktopCapturer.getSources({ types: ['window'] });
          const sbSrc = sources.find(s =>
            s.name.includes('Windows Sandbox') || s.name.includes('WindowsSandbox')
          );
          if (sbSrc) {
            callback({ video: sbSrc });
            return;
          }
        } catch (err) {
          debugLog(`[Sandbox] Capture error: ${err.message}`);
        }
      }
      // Default: deny
      callback({});
    });
  } catch (displayErr) {
    debugLog(`[DisplayMedia] Handler setup skipped: ${displayErr.message}`);
  }

  // Window will be loaded later (loading page first, then frontend)

  mainWindow.on('close', (e) => {
    if (!isQuitting && store.get('minimizeToTray')) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => { mainWindow = null; });

  if (isDev) {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }
}

// ── Application Menu (Keyboard Shortcuts) ─────────────────
function setupAppMenu() {
  const isMac = process.platform === 'darwin';
  const template = [
    // On macOS the first menu is the app name menu
    ...(isMac ? [{
      label: app.name,
      submenu: [
        { role: 'about' },
        { type: 'separator' },
        { role: 'quit' },
      ],
    }] : []),
    {
      label: 'View',
      submenu: [
        {
          label: 'Reload',
          accelerator: 'F5',
          click: () => { if (mainWindow) mainWindow.webContents.reload(); },
        },
        {
          label: 'Reload',
          accelerator: 'CmdOrCtrl+R',
          click: () => { if (mainWindow) mainWindow.webContents.reload(); },
        },
        {
          label: 'Force Reload',
          accelerator: 'CmdOrCtrl+Shift+R',
          click: () => {
            if (mainWindow) {
              mainWindow.webContents.session.clearCache().then(() => {
                mainWindow.webContents.reload();
              });
            }
          },
        },
        { type: 'separator' },
        {
          label: 'Toggle Developer Tools',
          accelerator: 'F12',
          click: () => { if (mainWindow) mainWindow.webContents.toggleDevTools(); },
        },
        {
          label: 'Toggle Developer Tools',
          accelerator: 'CmdOrCtrl+Shift+I',
          visible: false,
          click: () => { if (mainWindow) mainWindow.webContents.toggleDevTools(); },
        },
        { type: 'separator' },
        {
          label: 'Zoom In',
          accelerator: 'CmdOrCtrl+=',
          click: () => {
            if (mainWindow) {
              const zoom = mainWindow.webContents.getZoomLevel();
              mainWindow.webContents.setZoomLevel(zoom + 0.5);
            }
          },
        },
        {
          label: 'Zoom Out',
          accelerator: 'CmdOrCtrl+-',
          click: () => {
            if (mainWindow) {
              const zoom = mainWindow.webContents.getZoomLevel();
              mainWindow.webContents.setZoomLevel(zoom - 0.5);
            }
          },
        },
        {
          label: 'Reset Zoom',
          accelerator: 'CmdOrCtrl+0',
          click: () => { if (mainWindow) mainWindow.webContents.setZoomLevel(0); },
        },
      ],
    },
    {
      label: 'Navigation',
      submenu: [
        {
          label: 'Go Back',
          accelerator: 'Alt+Left',
          click: () => { if (mainWindow && mainWindow.webContents.canGoBack()) mainWindow.webContents.goBack(); },
        },
        {
          label: 'Go Forward',
          accelerator: 'Alt+Right',
          click: () => { if (mainWindow && mainWindow.webContents.canGoForward()) mainWindow.webContents.goForward(); },
        },
        { type: 'separator' },
        {
          label: 'Home',
          accelerator: 'CmdOrCtrl+H',
          click: () => {
            if (mainWindow) {
              mainWindow.loadURL(`http://localhost:${store.get('frontendPort')}`);
            }
          },
        },
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

// ── Tray ──────────────────────────────────────────────────
function createTray() {
  const iconPath = getIconPath();
  if (!iconPath) {
    tray = new Tray(nativeImage.createEmpty());
  } else {
    tray = new Tray(iconPath);
  }

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open ogenti',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.focus();
        }
      },
    },
    { type: 'separator' },
    {
      label: 'Settings',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
          mainWindow.loadURL(`http://localhost:${store.get('frontendPort')}/settings`);
        }
      },
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);

  tray.setToolTip('ogenti');
  tray.setContextMenu(contextMenu);
  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

// ── Backend & Runtime Launch ──────────────────────────────
async function startServices() {
  ensureDataDir();
  debugLog('Starting services...');

  const backendPort = store.get('backendPort');
  const frontendPort = store.get('frontendPort');
  const runtimePort = store.get('runtimePort');
  const dbPath = getDBPath();

  debugLog(`Ports: backend=${backendPort}, frontend=${frontendPort}, runtime=${runtimePort}`);
  debugLog(`DB Path: ${dbPath}`);
  debugLog(`Backend Path: ${getBackendPath()}`);
  debugLog(`Frontend Path: ${getFrontendPath()}`);
  debugLog(`Resources Path: ${resourcesPath}`);
  debugLog(`isDev: ${isDev}`);

  // Determine backend URL based on mode
  const effectiveBackendUrl = USE_CENTRAL_SERVER ? CENTRAL_BACKEND_URL : `http://localhost:${backendPort}`;
  const effectiveWsUrl = USE_CENTRAL_SERVER
    ? CENTRAL_BACKEND_URL.replace('https://', 'wss://').replace('http://', 'ws://')
    : `ws://localhost:${backendPort}`;
  debugLog(`Mode: ${USE_CENTRAL_SERVER ? 'CENTRAL SERVER' : 'LOCAL'}, Backend: ${effectiveBackendUrl}`);

  const runtimeToken = store.get('runtimeToken') || '';

  if (!USE_CENTRAL_SERVER) {
    // ── LOCAL MODE: Launch backend locally ──
    const env = {
      NODE_ENV: 'production',
      PORT: String(backendPort),
      DATABASE_URL: `file:${dbPath}`,
      JWT_SECRET: safeGet('jwtSecret') || generateSecret(),
      JWT_REFRESH_SECRET: safeGet('jwtRefreshSecret') || generateSecret(),
      ENCRYPTION_KEY: safeGet('encryptionKey') || generateSecret(),
      FRONTEND_URL: `http://localhost:${frontendPort}`,
      BACKEND_URL: `http://localhost:${backendPort}`,
      AGENT_RUNTIME_URL: `http://127.0.0.1:${runtimePort}`,
      CORS_ORIGINS: `http://localhost:${frontendPort}`,
      AGENT_RUNTIME_SECRET: safeGet('agentRuntimeSecret') || process.env.AGENT_RUNTIME_SECRET || generateSecret(),
    };

    const backendEnv = loadEnvFile(path.join(getBackendPath(), '.env'));
    const rootEnv = loadEnvFile(path.join(isDev ? path.resolve(__dirname, '..') : resourcesPath, '..', '.env'));
    debugLog(`[ENV] backend .env keys: ${Object.keys(backendEnv).join(', ')}`);

    const smtpHost = store.get('smtpHost') || backendEnv.SMTP_HOST || rootEnv.SMTP_HOST || process.env.SMTP_HOST || '';
    const smtpPort = store.get('smtpPort') || backendEnv.SMTP_PORT || rootEnv.SMTP_PORT || process.env.SMTP_PORT || '';
    const smtpSecure = store.get('smtpSecure') || backendEnv.SMTP_SECURE || rootEnv.SMTP_SECURE || process.env.SMTP_SECURE || '';
    const smtpUser = store.get('smtpUser') || backendEnv.SMTP_USER || rootEnv.SMTP_USER || process.env.SMTP_USER || '';
    const smtpPass = safeGet('smtpPass') || backendEnv.SMTP_PASS || rootEnv.SMTP_PASS || process.env.SMTP_PASS || '';
    const smtpFrom = store.get('smtpFrom') || backendEnv.SMTP_FROM || rootEnv.SMTP_FROM || process.env.SMTP_FROM || smtpUser;
    debugLog(`[SMTP] host=${smtpHost}, user=${smtpUser}, hasPass=${!!smtpPass}`);
    if (smtpHost) env.SMTP_HOST = smtpHost;
    if (smtpPort) env.SMTP_PORT = String(smtpPort);
    if (smtpSecure) env.SMTP_SECURE = smtpSecure;
    if (smtpUser) env.SMTP_USER = smtpUser;
    if (smtpPass) env.SMTP_PASS = smtpPass;
    if (smtpFrom) env.SMTP_FROM = smtpFrom;

    const stripeKey = safeGet('stripeSecretKey') || backendEnv.STRIPE_SECRET_KEY || rootEnv.STRIPE_SECRET_KEY || process.env.STRIPE_SECRET_KEY || '';
    const stripePublishable = backendEnv.STRIPE_PUBLISHABLE_KEY || rootEnv.STRIPE_PUBLISHABLE_KEY || process.env.STRIPE_PUBLISHABLE_KEY || '';
    const stripeWebhook = safeGet('stripeWebhookSecret') || backendEnv.STRIPE_WEBHOOK_SECRET || rootEnv.STRIPE_WEBHOOK_SECRET || process.env.STRIPE_WEBHOOK_SECRET || '';
    if (stripeKey) env.STRIPE_SECRET_KEY = stripeKey;
    if (stripePublishable) env.STRIPE_PUBLISHABLE_KEY = stripePublishable;
    if (stripeWebhook) env.STRIPE_WEBHOOK_SECRET = stripeWebhook;
    debugLog(`[Stripe] hasSecretKey=${!!stripeKey}, hasPublishableKey=${!!stripePublishable}`);

    if (!safeGet('jwtSecret')) {
      safeSet('jwtSecret', env.JWT_SECRET);
      safeSet('jwtRefreshSecret', env.JWT_REFRESH_SECRET);
    }
    if (!safeGet('encryptionKey')) safeSet('encryptionKey', env.ENCRYPTION_KEY);
    if (!safeGet('agentRuntimeSecret')) safeSet('agentRuntimeSecret', env.AGENT_RUNTIME_SECRET);

    backendProcess = await launchBackend(getBackendPath(), env, isDev);
  }

  const runtimeEnvSecret = (!USE_CENTRAL_SERVER && backendProcess)
    ? (safeGet('agentRuntimeSecret') || process.env.AGENT_RUNTIME_SECRET || '')
    : '';

  // Launch agent runtime (always local — it controls the user's OS)
  const runtimeEnv = {
    BACKEND_URL: effectiveBackendUrl,
    RUNTIME_PORT: String(runtimePort),
    AGENT_RUNTIME_SECRET: runtimeEnvSecret || '',
    RUNTIME_TOKEN: runtimeToken,
    LOG_LEVEL: 'INFO',
  };
  runtimeProcess = await launchRuntime(getRuntimePath(), runtimeEnv, isDev);

  // Launch frontend (Next.js standalone)
  const frontendEnv = {
    PORT: String(frontendPort),
    NEXT_PUBLIC_API_URL: `${effectiveBackendUrl}/api`,
    NEXT_PUBLIC_WS_URL: effectiveWsUrl,
  };
  frontendProcess = await launchFrontend(getFrontendPath(), frontendEnv, isDev);

  debugLog('All services launched, waiting for health checks...');

  if (!USE_CENTRAL_SERVER) {
    await waitForService(`http://localhost:${backendPort}/health`, 60000);
  }

  // Wait for frontend to be ready
  await waitForService(`http://localhost:${frontendPort}`, 60000);

  // Wait for agent runtime (optional — don't fail if it's not available)
  try {
    await waitForService(`http://localhost:${runtimePort}/health`, 15000);
    debugLog('Agent runtime is ready');
  } catch {
    debugLog('Agent runtime not ready (optional — will retry on execution)');
  }

  debugLog('All services are ready!');
  return { backendPort, frontendPort, runtimePort };
}

async function waitForService(url, timeout = 30000) {
  const start = Date.now();
  const urlObj = new URL(url);
  debugLog(`Waiting for service: ${url} (timeout ${timeout}ms)`);

  while (Date.now() - start < timeout) {
    try {
      await new Promise((resolve, reject) => {
        const req = http.get({
          hostname: '127.0.0.1',
          port: parseInt(urlObj.port),
          path: urlObj.pathname || '/',
          timeout: 3000,
        }, (res) => {
          res.resume(); // consume response
          if (res.statusCode >= 200 && res.statusCode < 400) {
            resolve();
          } else {
            reject(new Error(`HTTP ${res.statusCode}`));
          }
        });
        req.on('error', reject);
        req.on('timeout', () => { req.destroy(); reject(new Error('timeout')); });
      });
      debugLog(`Service ready: ${url} (${Date.now() - start}ms)`);
      return true;
    } catch {}
    await new Promise(r => setTimeout(r, 500));
  }
  throw new Error(`Service at ${url} did not start within ${timeout}ms`);
}

function generateSecret() {
  const crypto = require('crypto');
  return crypto.randomBytes(48).toString('base64url');
}

// ── IPC Handlers ──────────────────────────────────────────

// App control handlers
ipcMain.handle('app:minimize', () => mainWindow?.minimize());
ipcMain.handle('app:maximize', () => {
  if (mainWindow?.isMaximized()) mainWindow.unmaximize();
  else mainWindow?.maximize();
});
ipcMain.handle('app:close', () => {
  if (store.get('minimizeToTray')) mainWindow?.hide();
  else { isQuitting = true; app.quit(); }
});
ipcMain.handle('app:quit', () => { isQuitting = true; app.quit(); });

ipcMain.handle('app:get-config', () => ({
  backendPort: store.get('backendPort'),
  frontendPort: store.get('frontendPort'),
  runtimePort: store.get('runtimePort'),
  isDev,
  version: app.getVersion(),
  platform: process.platform,
}));

ipcMain.handle('app:open-external', (_, url) => {
  // Only allow http/https URLs to prevent file://, javascript:, or smb:// exploits
  if (typeof url === 'string' && /^https?:\/\//i.test(url)) {
    return shell.openExternal(url);
  }
  return Promise.reject(new Error('Only http/https URLs are allowed'));
});
ipcMain.handle('app:get-path', (_, name) => {
  // Restrict to safe path names
  const allowedPaths = ['userData', 'temp', 'downloads', 'desktop', 'documents'];
  if (!allowedPaths.includes(name)) {
    return Promise.reject(new Error(`Path '${name}' not allowed`));
  }
  return app.getPath(name);
});

ipcMain.handle('app:restart-services', async () => {
  await stopFrontend(frontendProcess);
  await stopBackend(backendProcess);
  await stopRuntime(runtimeProcess);
  const result = await startServices();
  return result;
});

// ── Windows Sandbox IPC ───────────────────────────────────
let sandboxProcess = null;
let sandboxCaptureMode = false;

ipcMain.handle('sandbox:check-available', () => {
  try {
    const wsbExe = path.join(process.env.WINDIR || 'C:\\Windows', 'System32', 'WindowsSandbox.exe');
    return fs.existsSync(wsbExe);
  } catch {
    return false;
  }
});

ipcMain.handle('sandbox:launch', async (_, config) => {
  try {
    // Generate .wsb configuration
    const mappedFolders = (config?.mappedFolders || []).map(f => `
    <MappedFolder>
      <HostFolder>${f.hostFolder}</HostFolder>
      <SandboxFolder>${f.sandboxFolder || ''}</SandboxFolder>
      <ReadOnly>${f.readOnly ? 'true' : 'false'}</ReadOnly>
    </MappedFolder>`).join('');

    const logonCmd = config?.logonCommand
      ? `<LogonCommand><Command>${config.logonCommand}</Command></LogonCommand>`
      : '';

    const memoryMB = config?.memoryMB || 4096;

    const wsbXml = `<Configuration>
  <VGpu>Enable</VGpu>
  <Networking>Enable</Networking>
  <MemoryInMB>${memoryMB}</MemoryInMB>
  <AudioInput>Disable</AudioInput>
  <VideoInput>Disable</VideoInput>
  <ClipboardRedirection>Enable</ClipboardRedirection>
  <PrinterRedirection>Disable</PrinterRedirection>
  <MappedFolders>${mappedFolders}
  </MappedFolders>
  ${logonCmd}
</Configuration>`;

    const wsbPath = path.join(app.getPath('temp'), 'ogenti-sandbox.wsb');
    fs.writeFileSync(wsbPath, wsbXml, 'utf-8');
    debugLog(`[Sandbox] Config written to ${wsbPath}`);

    // Launch Windows Sandbox
    sandboxProcess = spawn('cmd', ['/c', 'start', '', wsbPath], {
      detached: true,
      stdio: 'ignore',
      windowsHide: true,
    });
    sandboxProcess.unref();

    debugLog('[Sandbox] Launched Windows Sandbox');
    return { success: true };
  } catch (err) {
    debugLog(`[Sandbox] Launch error: ${err.message}`);
    return { success: false, error: err.message };
  }
});

ipcMain.handle('sandbox:stop', async () => {
  try {
    execSync('taskkill /F /IM WindowsSandbox.exe /T', { windowsHide: true, timeout: 5000 });
    // Also kill the client process
    try { execSync('taskkill /F /IM WindowsSandboxClient.exe /T', { windowsHide: true, timeout: 3000 }); } catch {}
    sandboxProcess = null;
    debugLog('[Sandbox] Stopped');
    return { success: true };
  } catch (err) {
    debugLog(`[Sandbox] Stop error: ${err.message}`);
    return { success: false, error: err.message };
  }
});

ipcMain.handle('sandbox:is-running', () => {
  try {
    const output = execSync('tasklist /FI "IMAGENAME eq WindowsSandboxClient.exe" /FO CSV /NH',
      { windowsHide: true, encoding: 'utf8', timeout: 3000 });
    return output.toLowerCase().includes('windowssandboxclient');
  } catch {
    return false;
  }
});

ipcMain.handle('sandbox:request-capture', () => {
  sandboxCaptureMode = true;
  return true;
});

ipcMain.handle('sandbox:get-thumbnail', async () => {
  try {
    const sources = await desktopCapturer.getSources({
      types: ['window'],
      thumbnailSize: { width: 1280, height: 720 },
    });
    const sb = sources.find(s =>
      s.name.includes('Windows Sandbox') || s.name.includes('WindowsSandbox')
    );
    if (sb) {
      return sb.thumbnail.toDataURL();
    }
    return null;
  } catch {
    return null;
  }
});

ipcMain.handle('sandbox:focus', () => {
  try {
    execSync(
      'powershell -Command "$ws = New-Object -ComObject wscript.shell; $ws.AppActivate(\'Windows Sandbox\')"',
      { windowsHide: true, timeout: 3000 }
    );
    return true;
  } catch {
    return false;
  }
});

ipcMain.handle('sandbox:focus-ogenti', () => {
  if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
    return true;
  }
  return false;
});

// ── Stripe Key Management ─────────────────────────────────
ipcMain.handle('stripe:get-config', () => ({
  hasSecretKey: !!safeGet('stripeSecretKey'),
  hasWebhookSecret: !!safeGet('stripeWebhookSecret'),
}));

ipcMain.handle('stripe:save-keys', (_, { secretKey, webhookSecret }) => {
  if (secretKey !== undefined) {
    if (secretKey) {
      safeSet('stripeSecretKey', secretKey);
    } else {
      try { store.delete('_enc_stripeSecretKey'); } catch(e) {}
      try { store.delete('stripeSecretKey'); } catch(e) {}
    }
  }
  if (webhookSecret !== undefined) {
    if (webhookSecret) {
      safeSet('stripeWebhookSecret', webhookSecret);
    } else {
      try { store.delete('_enc_stripeWebhookSecret'); } catch(e) {}
      try { store.delete('stripeWebhookSecret'); } catch(e) {}
    }
  }
  return { success: true, message: 'Stripe keys saved. Restart services to apply.' };
});

// ── SMTP Key Management ───────────────────────────────────
ipcMain.handle('smtp:get-config', () => ({
  host: store.get('smtpHost') || '',
  port: store.get('smtpPort') || '',
  secure: store.get('smtpSecure') || '',
  user: store.get('smtpUser') || '',
  hasPass: !!safeGet('smtpPass'),
  from: store.get('smtpFrom') || '',
}));

ipcMain.handle('smtp:save-config', (_, { host, port, secure, user, pass, from }) => {
  if (host !== undefined) store.set('smtpHost', host || '');
  if (port !== undefined) store.set('smtpPort', port || '');
  if (secure !== undefined) store.set('smtpSecure', secure || '');
  if (user !== undefined) store.set('smtpUser', user || '');
  if (pass !== undefined) {
    if (pass) { safeSet('smtpPass', pass); } else { try { store.delete('_enc_smtpPass'); store.delete('smtpPass'); } catch(e) {} }
  }
  if (from !== undefined) store.set('smtpFrom', from || '');
  return { success: true, message: 'SMTP settings saved. Restart services to apply.' };
});

// ── Runtime Token Management (Central Server Mode) ────────
ipcMain.handle('runtime:save-token', (_, token) => {
  store.set('runtimeToken', token || '');
  return { success: true };
});

ipcMain.handle('runtime:get-token', () => {
  return store.get('runtimeToken') || '';
});

ipcMain.handle('runtime:get-backend-url', () => {
  return USE_CENTRAL_SERVER ? CENTRAL_BACKEND_URL : `http://localhost:${store.get('backendPort')}`;
});

ipcMain.handle('runtime:is-central', () => USE_CENTRAL_SERVER);

// ── Agent Purchase Approval Dialog ────────────────────────
ipcMain.handle('agent:purchase-approval', async (_, { agentName, targetName, creditCost, reason }) => {
  if (!mainWindow) return { approved: false };
  const result = await dialog.showMessageBox(mainWindow, {
    type: 'question',
    title: 'Agent Purchase Request',
    message: `${agentName} wants to buy "${targetName}"`,
    detail: `Cost: ${creditCost} credits\nReason: ${reason || 'No reason given'}\n\nDo you approve this purchase?`,
    buttons: ['Approve', 'Reject'],
    defaultId: 1,
    cancelId: 1,
    noLink: true,
  });
  return { approved: result.response === 0 };
});

// ── Loading Page HTML ─────────────────────────────────────
function getLoadingHTML() {
  return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #000000;
    color: #ffffff;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    -webkit-app-region: drag;
    overflow: hidden;
    position: relative;
  }

  /* Subtle grid background */
  body::before {
    content: '';
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px);
    background-size: 64px 64px;
    pointer-events: none;
  }

  /* Radial glow */
  body::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 600px;
    height: 600px;
    background: radial-gradient(circle, rgba(255,255,255,0.03) 0%, transparent 70%);
    pointer-events: none;
  }

  .container {
    position: relative;
    z-index: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 32px;
  }

  .logo-text {
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.5px;
    color: #ffffff;
    margin-top: 16px;
    animation: textIn 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.3s both;
  }
  @keyframes textIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }

  /* Progress bar */
  .progress-wrap {
    width: 200px;
    animation: textIn 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.5s both;
  }
  .progress-track {
    width: 100%;
    height: 2px;
    background: #1a1a1a;
    border-radius: 2px;
    overflow: hidden;
  }
  .progress-bar {
    height: 100%;
    width: 30%;
    background: #ffffff;
    border-radius: 2px;
    animation: loading 2s ease-in-out infinite;
  }
  @keyframes loading {
    0% { width: 0%; margin-left: 0%; }
    50% { width: 40%; margin-left: 30%; }
    100% { width: 0%; margin-left: 100%; }
  }

  .status {
    font-size: 12px;
    font-weight: 400;
    color: #555555;
    letter-spacing: 0.3px;
    margin-top: 8px;
    text-align: center;
    animation: textIn 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.7s both;
  }

  /* Bottom footer */
  .footer {
    position: absolute;
    bottom: 24px;
    font-size: 11px;
    color: #333333;
    letter-spacing: 0.5px;
    animation: textIn 0.6s cubic-bezier(0.16, 1, 0.3, 1) 0.9s both;
  }
</style></head><body>
  <div class="container">
    <div class="logo-text">ogenti</div>
    <div class="progress-wrap">
      <div class="progress-track">
        <div class="progress-bar"></div>
      </div>
      <div class="status">Initializing services</div>
    </div>
  </div>
  <div class="footer">DESKTOP CLIENT</div>
</body></html>`;
}

// ── App Lifecycle ─────────────────────────────────────────
if (isDev) app.commandLine.appendSwitch('disable-http-cache');
app.whenReady().then(async () => {
  if (!gotTheLock) return; // Second instance — bail out silently

  debugLog(`ogenti starting. execPath=${process.execPath}`);
  debugLog(`userData=${app.getPath('userData')}`);

  try {
  // Show loading window immediately
  createMainWindow();
  if (!mainWindow || mainWindow.isDestroyed()) {
    debugLog('FATAL: mainWindow was destroyed immediately after creation');
    app.exit(1);
    return;
  }
  setupAppMenu();
  mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(getLoadingHTML())}`);
  createTray();
    // Kill any existing processes on our ports before starting
    killProcessesOnPorts();
    await startServices();

    // Aggressively clear ALL browser caches BEFORE loading the frontend
    if (mainWindow && !mainWindow.isDestroyed()) {
      const ses = mainWindow.webContents.session;
      try {
        await Promise.all([
          ses.clearCache(),
          ses.clearStorageData({ storages: ['cachestorage', 'serviceworkers', 'shadercache'] }),
          ses.clearCodeCaches({}),
        ]);
        debugLog('[Cache] Cleared browser cache, storage data, and code caches');
      } catch (cacheErr) {
        debugLog(`[Cache] Partial clear: ${cacheErr.message}`);
      }
    }

    // Navigate to the actual frontend (cache-busted)
    const frontendPort = store.get('frontendPort');
    if (!mainWindow || mainWindow.isDestroyed()) {
      debugLog('Window was destroyed during startup — recreating');
      createMainWindow();
    }
    mainWindow.loadURL(`http://localhost:${frontendPort}?_cb=${Date.now()}`);
    debugLog('App fully initialized');
  } catch (error) {
    debugLog(`STARTUP ERROR: ${error.stack || error.message}`);
    dialog.showErrorBox('ogenti — Startup Error', 
      `Failed to start services: ${error.message}\n\nCheck log: ${path.join(app.getPath('userData'), 'ogenti-debug.log')}`);
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin' && isQuitting) {
    app.quit();
  }
});

app.on('activate', () => {
  if (mainWindow) {
    mainWindow.show();
  }
});

let cleanupStarted = false;
app.on('before-quit', (e) => {
  if (cleanupStarted) return;
  cleanupStarted = true;
  isQuitting = true;
  e.preventDefault();
  const timeout = setTimeout(() => {
    try { killProcessesOnPorts(); } catch {}
    app.exit(0);
  }, 8000);
  const cleanupTasks = [
    stopFrontend(frontendProcess).catch(() => {}),
    stopRuntime(runtimeProcess).catch(() => {}),
  ];
  if (!USE_CENTRAL_SERVER && backendProcess) {
    cleanupTasks.push(stopBackend(backendProcess).catch(() => {}));
  }
  Promise.all(cleanupTasks).finally(() => {
    clearTimeout(timeout);
    try { killProcessesOnPorts(); } catch {}
    app.exit(0);
  });
});

// Single instance lock is handled at the top of the file
