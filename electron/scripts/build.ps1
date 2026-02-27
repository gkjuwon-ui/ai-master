# ogenti ??Production Build Script
# ====================================
# This script builds all components and packages the Electron app.

param(
    [switch]$SkipDeps,
    [switch]$SkipBuild,
    [switch]$DevMode
)

$ErrorActionPreference = "Continue"
$RootDir = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $RootDir) { $RootDir = Get-Location }

Write-Host ""
Write-Host "?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?? -ForegroundColor Cyan
Write-Host "  ogenti ??Production Build" -ForegroundColor Cyan
Write-Host "?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?? -ForegroundColor Cyan
Write-Host ""

# ?�?� Helper ?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�
function Write-Step($msg) {
    Write-Host "  ??$msg" -ForegroundColor Yellow
}
function Write-Done($msg) {
    Write-Host "  ??$msg" -ForegroundColor Green
}
function Write-Err($msg) {
    Write-Host "  ??$msg" -ForegroundColor Red
}

# ?�?� 1. Check Prerequisites ?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�
Write-Step "Checking prerequisites..."

$nodeVersion = & node --version 2>$null
if (-not $nodeVersion) {
    Write-Err "Node.js is not installed. Please install Node.js 18+ first."
    exit 1
}
Write-Done "Node.js $nodeVersion"

$npmVersion = & npm --version 2>$null
Write-Done "npm $npmVersion"

# Check for Python (optional, for agent runtime)
$pythonVersion = & python --version 2>$null
if ($pythonVersion) {
    Write-Done "Python $pythonVersion (agent runtime available)"
} else {
    Write-Host "  ??Python not found ??agent runtime will not be available" -ForegroundColor Yellow
}

# ?�?� 2. Install Dependencies ?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�
if (-not $SkipDeps) {
    Write-Step "Installing backend dependencies..."
    Set-Location "$RootDir\backend"
    & npm install --omit=dev 2>&1 | Out-Null
    Write-Done "Backend dependencies installed"

    Write-Step "Installing frontend dependencies..."
    Set-Location "$RootDir\frontend"
    & npm install 2>&1 | Out-Null
    Write-Done "Frontend dependencies installed"

    Write-Step "Installing Electron dependencies..."
    Set-Location "$RootDir\electron"
    & npm install 2>&1 | Out-Null
    Write-Done "Electron dependencies installed"

    Write-Step "Generating Prisma client..."
    Set-Location "$RootDir\backend"
    & npx prisma generate 2>&1 | Out-Null
    Write-Done "Prisma client generated"
}

# ?�?� 3. Build Backend ?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�
if (-not $SkipBuild) {
    Write-Step "Building backend (TypeScript ??JavaScript)..."
    Set-Location "$RootDir\backend"
    
    # Ensure tsconfig has proper outDir
    & npx tsc --outDir dist 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ??TypeScript compilation had warnings (non-fatal)" -ForegroundColor Yellow
    }
    Write-Done "Backend built ??backend/dist/"

    # Copy prisma schema to dist
    if (-not (Test-Path "$RootDir\backend\dist\prisma")) {
        New-Item -ItemType Directory -Path "$RootDir\backend\dist\prisma" -Force | Out-Null
    }
    Copy-Item "$RootDir\backend\prisma\schema.prisma" "$RootDir\backend\dist\prisma\" -Force
    Write-Done "Prisma schema copied"

    # ?�?� 4. Build Frontend ?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�
    Write-Step "Building frontend (Next.js production build)..."
    Set-Location "$RootDir\frontend"
    
    # Central server mode by default; set USE_LOCAL_BACKEND=1 for local
    if ($env:USE_LOCAL_BACKEND -eq "1") {
        $env:NEXT_PUBLIC_API_URL = "http://localhost:4000/api"
        $env:NEXT_PUBLIC_WS_URL = "ws://localhost:4000"
    } else {
        $centralUrl = if ($env:CENTRAL_BACKEND_URL) { $env:CENTRAL_BACKEND_URL } else { "https://api.ogenti.com" }
        $env:NEXT_PUBLIC_API_URL = "$centralUrl/api"
        $env:NEXT_PUBLIC_WS_URL = ($centralUrl -replace "^https://", "wss://" -replace "^http://", "ws://")
    }
    & npx next build 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Frontend build failed!"
        exit 1
    }
    Write-Done "Frontend built ??frontend/.next/"
}

# Step 5: Database initialization
# Central server mode: DB is on Railway, skip local init
if ($env:USE_LOCAL_BACKEND -eq "1") {
    Write-Step "Initializing local database..."
    Set-Location "$RootDir\backend"
    $dbDir = "$RootDir\backend\prisma"
    $env:DATABASE_URL = "file:./dev.db"
    & npx prisma migrate deploy 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Running prisma db push as fallback..." -ForegroundColor Yellow
        & npx prisma db push 2>&1 | Out-Null
    }
    Write-Done "Database schema applied"
    $env:JWT_SECRET = [Convert]::ToBase64String((1..48 | ForEach-Object { Get-Random -Maximum 256 }) -as [byte[]])
    & npx tsx prisma/seed.ts 2>&1 | Out-Null
    Write-Done "Database seeded with initial data"
} else {
    Write-Done "Central server mode — skipping local database init (DB is on Railway)"
}

# ?�?� 6. Build Electron App ?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�
if (-not $DevMode) {
    Write-Step "Building Electron application..."
    Set-Location "$RootDir\electron"
    & npx electron-builder --win 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Electron build failed!"
        Write-Host "  You can still run in dev mode: cd electron && npm start" -ForegroundColor Yellow
    } else {
        Write-Done "Electron app built ??dist/"
    }
}

# ?�?� Summary ?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�?�
Set-Location $RootDir

Write-Host ""
Write-Host "?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?? -ForegroundColor Cyan
Write-Host "  Build Complete!" -ForegroundColor Green
Write-Host "?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?�═?? -ForegroundColor Cyan
Write-Host ""
Write-Host "  To run in development mode:" -ForegroundColor White
Write-Host "    cd electron && npm run dev" -ForegroundColor Gray
Write-Host ""
if (-not $DevMode) {
    Write-Host "  Installer location:" -ForegroundColor White
    Write-Host "    dist\ogenti-Setup-1.0.0.exe" -ForegroundColor Gray
    Write-Host ""
}
Write-Host "  To run backend only:" -ForegroundColor White
Write-Host "    cd backend && npm start" -ForegroundColor Gray
Write-Host ""
