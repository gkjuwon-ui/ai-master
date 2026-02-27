/**
 * Agent Runtime launcher — spawns the Python FastAPI agent runtime.
 * Auto-installs missing Python dependencies before starting.
 */

const { spawn, execSync } = require('child_process');
const path = require('path');
const fs = require('fs');
const http = require('http');
const kill = require('tree-kill');

let runtimeProc = null;

/**
 * Find a working Python command (python or python3).
 * Returns the command string or null.
 */
function findPython() {
  const candidates = process.platform === 'win32'
    ? ['python', 'python3', 'py -3']
    : ['python3', 'python'];

  for (const cmd of candidates) {
    try {
      const ver = execSync(`${cmd} --version`, { windowsHide: true, timeout: 5000, encoding: 'utf8' }).trim();
      if (ver.includes('Python 3')) {
        console.log(`[Runtime] Found Python: ${cmd} → ${ver}`);
        return cmd;
      }
    } catch {}
  }
  return null;
}

/**
 * Install missing Python packages from requirements.txt.
 */
function installDeps(pythonCmd, runtimePath) {
  const reqFile = path.join(runtimePath, 'requirements.txt');
  if (!fs.existsSync(reqFile)) {
    console.log('[Runtime] No requirements.txt found, skipping dep install');
    return;
  }

  // Quick check: try importing key modules
  const testImports = 'import fastapi, uvicorn, httpx, loguru, mss, pyautogui, pydantic';
  try {
    execSync(`${pythonCmd} -c "${testImports}"`, { windowsHide: true, timeout: 15000, encoding: 'utf8' });
    console.log('[Runtime] All Python dependencies available');
    return;
  } catch {
    console.log('[Runtime] Missing Python dependencies, installing...');
  }

  try {
    const result = execSync(
      `${pythonCmd} -m pip install --quiet --disable-pip-version-check -r "${reqFile}"`,
      { windowsHide: true, timeout: 120000, encoding: 'utf8', cwd: runtimePath }
    );
    console.log(`[Runtime] Dependencies installed: ${result.trim() || 'OK'}`);
  } catch (err) {
    console.warn(`[Runtime] pip install failed: ${err.message}`);
  }
}

/**
 * Check if runtime is healthy (HTTP GET /health).
 */
function checkHealth(port, timeoutMs = 3000) {
  return new Promise((resolve) => {
    const req = http.get({ hostname: '127.0.0.1', port, path: '/health', timeout: timeoutMs }, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => { req.destroy(); resolve(false); });
  });
}

async function launchRuntime(runtimePath, env, isDev) {
  const pythonCmd = findPython();
  if (!pythonCmd) {
    console.warn('[Runtime] Python 3 not found — agent runtime will not start');
    console.warn('[Runtime] Install Python 3.10+ from https://www.python.org/downloads/');
    return null;
  }

  // Auto-install missing dependencies
  installDeps(pythonCmd, runtimePath);

  const runtimePort = parseInt(env.RUNTIME_PORT || '5000', 10);

  // ── AGGRESSIVE PORT CLEANUP: Kill any old runtime on this port ──
  try {
    const netstatOut = execSync('netstat -ano', { windowsHide: true, encoding: 'utf8', timeout: 5000 });
    netstatOut.split('\n').forEach(line => {
      const m = line.match(new RegExp(`:\\s*${runtimePort}\\s+.*?LISTENING\\s+(\\d+)`));
      if (m) {
        const pid = parseInt(m[1]);
        if (pid && pid !== process.pid && pid !== 0) {
          try {
            execSync(`taskkill /F /PID ${pid}`, { windowsHide: true, timeout: 3000 });
            console.log(`[Runtime] Killed stale process PID ${pid} on port ${runtimePort}`);
          } catch {}
        }
      }
    });
  } catch (e) {
    console.log(`[Runtime] Port cleanup note: ${e.message}`);
  }

  // ── ENV: Force Python to use ONLY the runtime directory for imports ──
  const fullEnv = {
    ...process.env,
    ...env,
    PYTHONPATH: runtimePath,                   // Force module search to runtime dir
    PYTHONDONTWRITEBYTECODE: '1',              // No __pycache__ creation
    PYTHONUNBUFFERED: '1',                     // Immediate stdout/stderr
  };
  // Remove any inherited PYTHONPATH that might point elsewhere
  // (our explicit set above takes priority)
  console.log(`[Runtime] Path: ${runtimePath}`);
  console.log(`[Runtime] Python: ${pythonCmd}`);
  console.log(`[Runtime] Port: ${runtimePort}`);

  // Small delay after port kill to ensure port is released
  await new Promise(r => setTimeout(r, 500));

  return new Promise((resolve) => {
    // Use absolute path to main.py to avoid any cwd confusion
    const mainPyPath = path.join(runtimePath, 'main.py');
    console.log(`[Runtime] Launching: ${pythonCmd} "${mainPyPath}"`);
    runtimeProc = spawn(pythonCmd, [mainPyPath], {
      cwd: runtimePath,
      env: fullEnv,
      stdio: ['pipe', 'pipe', 'pipe'],
      shell: true,
      windowsHide: true,
    });

    let started = false;
    let earlyExit = false;

    runtimeProc.stdout?.on('data', (data) => {
      const msg = data.toString().trim();
      if (msg) console.log(`[Runtime] ${msg}`);
    });

    runtimeProc.stderr?.on('data', (data) => {
      const msg = data.toString().trim();
      if (msg) console.log(`[Runtime:err] ${msg}`);
    });

    runtimeProc.on('error', (err) => {
      console.warn(`[Runtime] Process error: ${err.message}`);
      if (!started) { started = true; resolve(null); }
    });

    runtimeProc.on('exit', (code) => {
      console.log(`[Runtime] Exited with code ${code}`);
      if (!started) { earlyExit = true; started = true; resolve(null); }
      runtimeProc = null;
    });

    // Poll health endpoint instead of fixed timeout
    const pollInterval = setInterval(async () => {
      if (earlyExit) {
        clearInterval(pollInterval);
        return;
      }
      const healthy = await checkHealth(runtimePort);
      if (healthy && !started) {
        started = true;
        clearInterval(pollInterval);
        console.log(`[Runtime] Health check passed on port ${runtimePort}`);
        resolve(runtimeProc);
      }
    }, 500);

    // Fallback: give up after 20 seconds
    setTimeout(() => {
      clearInterval(pollInterval);
      if (!started) {
        started = true;
        console.warn('[Runtime] Health check timeout after 20s — resolving anyway');
        resolve(runtimeProc);
      }
    }, 20000);
  });
}

async function stopRuntime() {
  if (runtimeProc && runtimeProc.pid) {
    return new Promise((resolve) => {
      kill(runtimeProc.pid, 'SIGTERM', (err) => {
        if (err) console.error('Failed to kill runtime:', err);
        runtimeProc = null;
        resolve();
      });
    });
  }
}

module.exports = { launchRuntime, stopRuntime };
