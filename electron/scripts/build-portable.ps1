# ogenti — Portable Build Script
# Creates a portable, self-contained app directory without code signing

$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$electronDir = Join-Path $root "electron"
$distDir = Join-Path $root "dist"
$appDir = Join-Path $distDir "ogenti-win-x64"

Write-Host "`n=== ogenti Portable Build ===" -ForegroundColor Cyan

# ── Clean previous build ──
if (Test-Path $appDir) {
    Write-Host "Cleaning previous build..." -ForegroundColor Yellow
    Remove-Item $appDir -Recurse -Force
}
New-Item -ItemType Directory -Path $appDir -Force | Out-Null

# ── Step 1: Get Electron binary ──
Write-Host "`n[1/6] Preparing Electron binary..." -ForegroundColor Green

$electronCache = Join-Path $env:LOCALAPPDATA "electron\Cache"
$electronExe = $null

# Check electron cache
if (Test-Path $electronCache) {
    $electronZip = Get-ChildItem $electronCache -Filter "electron-v*-win32-x64.zip" -Recurse | Select-Object -First 1
    if ($electronZip) {
        Write-Host "  Found cached Electron: $($electronZip.Name)"
        $tempExtract = Join-Path $distDir "electron-temp"
        if (Test-Path $tempExtract) { Remove-Item $tempExtract -Recurse -Force }
        Expand-Archive $electronZip.FullName -DestinationPath $tempExtract -Force
        
        # Copy all Electron files to app directory
        Copy-Item "$tempExtract\*" $appDir -Recurse -Force
        Remove-Item $tempExtract -Recurse -Force
        $electronExe = Join-Path $appDir "electron.exe"
    }
}

# Fallback: use node_modules electron
if (-not $electronExe -or -not (Test-Path $electronExe)) {
    $nodeElectron = Join-Path $electronDir "node_modules\electron\dist"
    if (Test-Path $nodeElectron) {
        Write-Host "  Using node_modules electron..."
        Copy-Item "$nodeElectron\*" $appDir -Recurse -Force
        $electronExe = Join-Path $appDir "electron.exe"
    } else {
        Write-Host "  ERROR: No Electron binary found!" -ForegroundColor Red
        exit 1
    }
}

# Rename electron.exe to ogenti.exe
$appExe = Join-Path $appDir "ogenti.exe"
if (Test-Path $electronExe) {
    Rename-Item $electronExe $appExe
    Write-Host "  -> ogenti.exe created"
}

# ── Step 2: Copy app source files ──
Write-Host "`n[2/6] Copying app files..." -ForegroundColor Green

$appResources = Join-Path $appDir "resources\app"
New-Item -ItemType Directory -Path $appResources -Force | Out-Null

# Copy Electron app files
$appFiles = @("main.js", "preload.js", "backend-launcher.js", "runtime-launcher.js", "frontend-launcher.js", "package.json")
foreach ($f in $appFiles) {
    $src = Join-Path $electronDir $f
    if (Test-Path $src) {
        Copy-Item $src $appResources -Force
        Write-Host "  + $f"
    }
}

# Copy resources folder
$resSrc = Join-Path $electronDir "resources"
$resDst = Join-Path $appResources "resources"
if (Test-Path $resSrc) {
    Copy-Item $resSrc $resDst -Recurse -Force
    Write-Host "  + resources/"
}

# Copy node_modules for electron app
$nodeModSrc = Join-Path $electronDir "node_modules"
$nodeModDst = Join-Path $appResources "node_modules"
if (Test-Path $nodeModSrc) {
    Write-Host "  + node_modules/ (this may take a moment...)"
    Copy-Item $nodeModSrc $nodeModDst -Recurse -Force
}

# ── Step 3: Copy backend ──
Write-Host "`n[3/6] Copying backend..." -ForegroundColor Green

$backendDst = Join-Path $appDir "resources\backend"
New-Item -ItemType Directory -Path $backendDst -Force | Out-Null

$backendSrc = Join-Path $root "backend"
# Copy compiled code, prisma, and package.json (NOT node_modules — it's empty due to workspace hoisting)
$backendItems = @("dist", "prisma", "package.json")
foreach ($item in $backendItems) {
    $src = Join-Path $backendSrc $item
    if (Test-Path $src) {
        $dst = Join-Path $backendDst $item
        if ((Get-Item $src).PSIsContainer) {
            Copy-Item $src $dst -Recurse -Force
        } else {
            Copy-Item $src $dst -Force
        }
        Write-Host "  + backend/$item"
    }
}

# Create uploads and logs directories
New-Item -ItemType Directory -Path (Join-Path $backendDst "uploads") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $backendDst "logs") -Force | Out-Null
Write-Host "  + backend/uploads/"
Write-Host "  + backend/logs/"

# Install production dependencies in the copied backend (workspace hoisting leaves backend/node_modules empty)
Write-Host "  Installing production dependencies..." -ForegroundColor Yellow
Push-Location $backendDst
try {
    # Find npm.cmd explicitly (not .ps1)
    $npmCmd = "npm.cmd"
    $npmFullPath = Get-Command npm -ErrorAction SilentlyContinue | Where-Object { $_.Source -like "*.cmd" } | Select-Object -First 1 -ExpandProperty Source
    if ($npmFullPath) {
        $npmCmd = $npmFullPath
    } else {
        $commonPaths = @("C:\Program Files\nodejs\npm.cmd", "$env:APPDATA\nvm\current\npm.cmd", "$env:LOCALAPPDATA\Programs\nodejs\npm.cmd")
        foreach ($p in $commonPaths) {
            if (Test-Path $p) { $npmCmd = $p; break }
        }
    }

    # Find npx in the same directory as npm
    $npxCmd = Join-Path (Split-Path $npmCmd -Parent) "npx.cmd"
    if (-not (Test-Path $npxCmd)) { $npxCmd = "npx.cmd" }

    Write-Host "  Using npm: $npmCmd"

    # Install production deps only
    $installOutput = & cmd /c "`"$npmCmd`" install --production 2>&1"
    $installOutput | ForEach-Object { Write-Host "    $_" }
    if ($LASTEXITCODE -ne 0) { throw "npm install failed with exit code $LASTEXITCODE" }

    # Generate Prisma client
    $prismaOutput = & cmd /c "`"$npxCmd`" prisma generate 2>&1"
    $prismaOutput | ForEach-Object { Write-Host "    $_" }
    if ($LASTEXITCODE -ne 0) { throw "prisma generate failed with exit code $LASTEXITCODE" }

    Write-Host "  + backend/node_modules/ (production deps installed)" -ForegroundColor Green
} catch {
    Write-Host "  ERROR: Failed to install backend deps: $_" -ForegroundColor Red
    throw $_
} finally {
    Pop-Location
}

# ── Step 4: Copy frontend (standalone) ──
Write-Host "`n[4/6] Copying frontend standalone build..." -ForegroundColor Green

$frontendDst = Join-Path $appDir "resources\frontend"
New-Item -ItemType Directory -Path $frontendDst -Force | Out-Null

# Copy standalone output
$standaloneSrc = Join-Path $root "frontend\.next\standalone"
if (Test-Path $standaloneSrc) {
    $standaloneDst = Join-Path $frontendDst "standalone"
    Copy-Item $standaloneSrc $standaloneDst -Recurse -Force
    Write-Host "  + frontend/standalone/"
}

# Copy the entire .next directory into standalone/frontend/.next
$dotNextSrc = Join-Path $root "frontend\.next"
$dotNextDst = Join-Path $frontendDst "standalone\frontend\.next"
if (Test-Path $dotNextSrc) {
    # Remove existing .next if it exists (standalone already has a partial one)
    if (Test-Path $dotNextDst) {
        Remove-Item $dotNextDst -Recurse -Force -ErrorAction SilentlyContinue
    }
    Copy-Item $dotNextSrc $dotNextDst -Recurse -Force
    Write-Host "  + frontend/.next/ (complete)"
}

# ── Step 5: Copy agent runtime ──
Write-Host "`n[5/6] Copying agent runtime..." -ForegroundColor Green

$runtimeDst = Join-Path $appDir "resources\agent-runtime"
New-Item -ItemType Directory -Path $runtimeDst -Force | Out-Null

$runtimeSrc = Join-Path $root "agent-runtime"
Get-ChildItem $runtimeSrc -Filter "*.py" | ForEach-Object {
    Copy-Item $_.FullName $runtimeDst -Force
    Write-Host "  + $($_.Name)"
}

# Copy subdirectories
$runtimeDirs = @("core", "plugins")
foreach ($dir in $runtimeDirs) {
    $src = Join-Path $runtimeSrc $dir
    if (Test-Path $src) {
        $dst = Join-Path $runtimeDst $dir
        Copy-Item $src $dst -Recurse -Force
        Write-Host "  + $dir/"
    }
}

# Copy requirements.txt
$reqSrc = Join-Path $runtimeSrc "requirements.txt"
if (Test-Path $reqSrc) {
    Copy-Item $reqSrc $runtimeDst -Force
    Write-Host "  + requirements.txt"
}

# ── Step 6: Create launcher script ──
Write-Host "`n[6/6] Creating launcher..." -ForegroundColor Green

$launcherContent = @"
@echo off
cd /d "%~dp0"
start "" "ogenti.exe"
"@
$launcherContent | Out-File (Join-Path $appDir "Start ogenti.bat") -Encoding ascii

# ── Summary ──
$totalSize = (Get-ChildItem $appDir -Recurse -File | Measure-Object -Property Length -Sum).Sum
$sizeMB = [math]::Round($totalSize / 1MB, 1)

Write-Host "`n=== Build Complete ===" -ForegroundColor Cyan
Write-Host "  Output: $appDir" -ForegroundColor White
Write-Host "  Size:   $sizeMB MB" -ForegroundColor White
Write-Host "  Run:    'ogenti.exe' or 'Start ogenti.bat'" -ForegroundColor White
Write-Host ""
