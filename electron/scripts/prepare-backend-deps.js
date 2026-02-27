/**
 * prepare-backend-deps.js
 * 
 * Ensures the backend/node_modules directory contains all production
 * dependencies before Electron packaging. In npm workspaces, dependencies
 * are hoisted to the root node_modules/, leaving backend/node_modules empty.
 * This script copies them down so electron-builder can package them.
 */

const path = require('path');
const fs = require('fs');

const rootDir = path.resolve(__dirname, '..', '..');
const backendDir = path.join(rootDir, 'backend');
const rootNodeModules = path.join(rootDir, 'node_modules');
const backendNodeModules = path.join(backendDir, 'node_modules');
const backendPkg = require(path.join(backendDir, 'package.json'));

console.log('\n=== Preparing backend dependencies for Electron packaging ===\n');

// Read production dependencies from backend/package.json
const deps = backendPkg.dependencies || {};
const depNames = Object.keys(deps);

if (depNames.length === 0) {
  console.log('No dependencies found in backend/package.json');
  process.exit(0);
}

console.log(`Found ${depNames.length} production dependencies to resolve.\n`);

// Clean existing backend/node_modules
// BUT preserve .prisma generated client first (created by prisma generate in build:backend)
const backendPrismaBackup = path.join(rootDir, '.prisma-backup');
const existingPrisma = path.join(backendNodeModules, '.prisma');
if (fs.existsSync(existingPrisma)) {
  console.log('  Saving generated .prisma client before clean...');
  if (fs.existsSync(backendPrismaBackup)) fs.rmSync(backendPrismaBackup, { recursive: true });
  fs.cpSync(existingPrisma, backendPrismaBackup, { recursive: true });
}
if (fs.existsSync(backendNodeModules)) {
  console.log('Cleaning existing backend/node_modules...');
  fs.rmSync(backendNodeModules, { recursive: true, force: true });
}
fs.mkdirSync(backendNodeModules, { recursive: true });

// Track all copied packages to avoid duplicates
const copied = new Set();

/**
 * Copy a package from root node_modules to backend/node_modules,
 * then recursively process all its dependencies.
 */
function copyDep(depName) {
  if (copied.has(depName)) return;
  copied.add(depName);

  const srcPath = path.join(rootNodeModules, depName);
  const destPath = path.join(backendNodeModules, depName);

  if (!fs.existsSync(srcPath)) {
    // Some deps are Node.js built-ins (like 'util', 'path', etc) — skip them
    return;
  }

  // For scoped packages, ensure parent directory exists
  if (depName.startsWith('@')) {
    const scopeDir = path.join(backendNodeModules, depName.split('/')[0]);
    if (!fs.existsSync(scopeDir)) {
      fs.mkdirSync(scopeDir, { recursive: true });
    }
  }

  if (!fs.existsSync(destPath)) {
    fs.cpSync(srcPath, destPath, { recursive: true });
  }

  // Read this package's dependencies and copy them recursively
  const depPkgPath = path.join(srcPath, 'package.json');
  if (fs.existsSync(depPkgPath)) {
    try {
      const depPkg = JSON.parse(fs.readFileSync(depPkgPath, 'utf8'));
      const subDeps = Object.keys(depPkg.dependencies || {});
      for (const subDep of subDeps) {
        copyDep(subDep);
      }
    } catch (e) {
      // ignore parse errors
    }
  }

  // ALSO scan nested node_modules inside this package for their deps
  scanNestedNodeModules(srcPath);
}

/**
 * Scan nested node_modules directories within a package for packages
 * that depend on modules at the root level (hoisted deps).
 * e.g. concat-stream/node_modules/readable-stream -> needs process-nextick-args
 */
function scanNestedNodeModules(pkgPath) {
  const nestedNM = path.join(pkgPath, 'node_modules');
  if (!fs.existsSync(nestedNM)) return;

  const entries = fs.readdirSync(nestedNM);
  for (const entry of entries) {
    if (entry.startsWith('.')) continue;
    const entryPath = path.join(nestedNM, entry);

    if (entry.startsWith('@') && fs.statSync(entryPath).isDirectory()) {
      // Scoped package — iterate into it
      const scopedEntries = fs.readdirSync(entryPath);
      for (const scopedEntry of scopedEntries) {
        const scopedPkgPath = path.join(entryPath, scopedEntry, 'package.json');
        if (fs.existsSync(scopedPkgPath)) {
          try {
            const pkg = JSON.parse(fs.readFileSync(scopedPkgPath, 'utf8'));
            const subDeps = Object.keys(pkg.dependencies || {});
            for (const dep of subDeps) { copyDep(dep); }
          } catch (e) {}
        }
        scanNestedNodeModules(path.join(entryPath, scopedEntry));
      }
    } else if (fs.statSync(entryPath).isDirectory()) {
      const nestedPkgPath = path.join(entryPath, 'package.json');
      if (fs.existsSync(nestedPkgPath)) {
        try {
          const pkg = JSON.parse(fs.readFileSync(nestedPkgPath, 'utf8'));
          const subDeps = Object.keys(pkg.dependencies || {});
          for (const dep of subDeps) { copyDep(dep); }
        } catch (e) {}
      }
      // Recurse deeper
      scanNestedNodeModules(entryPath);
    }
  }
}

// Copy all direct dependencies and their transitive deps
for (const depName of depNames) {
  process.stdout.write(`  Copying ${depName}...`);
  copyDep(depName);
  console.log(' ✓');
}

// Create .bin shims for critical CLI tools (prisma)
const binDir = path.join(backendNodeModules, '.bin');
if (!fs.existsSync(binDir)) fs.mkdirSync(binDir, { recursive: true });

// Copy .bin entries from root for packages we copied
const rootBinDir = path.join(rootNodeModules, '.bin');
if (fs.existsSync(rootBinDir)) {
  const criticalBins = ['prisma', 'prisma.cmd', 'prisma.ps1'];
  for (const binName of criticalBins) {
    const srcBin = path.join(rootBinDir, binName);
    const destBin = path.join(binDir, binName);
    if (fs.existsSync(srcBin) && !fs.existsSync(destBin)) {
      // Read the shim and fix relative paths
      const content = fs.readFileSync(srcBin, 'utf8');
      // Root .bin shims point to ../prisma/... which is correct for backend/node_modules too
      fs.writeFileSync(destBin, content);
      console.log(`  Created .bin/${binName}`);
    }
  }
}

// Restore .prisma generated client from backup (built by prisma generate in build:backend)
// This ensures the Prisma client matches the current schema, not a stale root copy
const prismaDest = path.join(backendNodeModules, '.prisma');
if (fs.existsSync(backendPrismaBackup)) {
  console.log('  Restoring saved .prisma client...');
  if (fs.existsSync(prismaDest)) fs.rmSync(prismaDest, { recursive: true, force: true });
  fs.cpSync(backendPrismaBackup, prismaDest, { recursive: true });
  fs.rmSync(backendPrismaBackup, { recursive: true, force: true });
  console.log('  ✓ .prisma client restored from build');
} else {
  // Fallback: copy from root (may be stale)
  const prismaSrc = path.join(rootNodeModules, '.prisma');
  if (fs.existsSync(prismaSrc) && !fs.existsSync(prismaDest)) {
    console.log('  Copying .prisma (generated client) from root (fallback)...');
    fs.cpSync(prismaSrc, prismaDest, { recursive: true });
  }
}

// Copy prisma engine binary directory
const prismaEngineSrc = path.join(rootNodeModules, 'prisma');
const prismaEngineDest = path.join(backendNodeModules, 'prisma');
if (fs.existsSync(prismaEngineSrc) && !fs.existsSync(prismaEngineDest)) {
  console.log('  Copying prisma engine...');
  fs.cpSync(prismaEngineSrc, prismaEngineDest, { recursive: true });
}

// Copy @prisma/engines (required by prisma CLI for migrate/db push)
const prismaEnginesPkgSrc = path.join(rootNodeModules, '@prisma', 'engines');
const prismaEnginesPkgDest = path.join(backendNodeModules, '@prisma', 'engines');
if (fs.existsSync(prismaEnginesPkgSrc) && !fs.existsSync(prismaEnginesPkgDest)) {
  console.log('  Copying @prisma/engines...');
  const prismaScope = path.join(backendNodeModules, '@prisma');
  if (!fs.existsSync(prismaScope)) fs.mkdirSync(prismaScope, { recursive: true });
  fs.cpSync(prismaEnginesPkgSrc, prismaEnginesPkgDest, { recursive: true });
}

// Count what we packaged
const countPackages = (dir) => {
  let count = 0;
  if (!fs.existsSync(dir)) return 0;
  for (const entry of fs.readdirSync(dir)) {
    if (entry.startsWith('.')) continue;
    const full = path.join(dir, entry);
    if (!fs.statSync(full).isDirectory()) continue;
    if (entry.startsWith('@')) {
      count += fs.readdirSync(full).filter(e => {
        const p = path.join(full, e);
        return fs.statSync(p).isDirectory();
      }).length;
    } else {
      count++;
    }
  }
  return count;
};

const totalPackages = countPackages(backendNodeModules);
console.log(`\n✓ ${totalPackages} packages copied to backend/node_modules`);
console.log(`  (${copied.size} unique dependency names resolved)`);

// Verify critical dependencies exist
const critical = ['express', 'cors', 'helmet', 'jsonwebtoken', '@prisma/client', 'ws', 'stripe'];
const missing = critical.filter((dep) => !fs.existsSync(path.join(backendNodeModules, dep)));
if (missing.length > 0) {
  console.error(`\nERROR: Missing critical dependencies: ${missing.join(', ')}`);
  process.exit(1);
}

console.log('✓ All critical dependencies verified\n');
