# GrowthCrew one-click local deployment (called by setup.bat; can also run directly:
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1)
# What it does: check docker -> generate secrets -> write .env -> compose up --build
#               -> wait for backend health -> print access URLs
# No absolute paths anywhere; everything is relative to this script's folder.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function New-UrlSafeKey([int]$bytes) {
    $b = New-Object byte[] $bytes
    # Create()/GetBytes() works on both Windows PowerShell 5.1 (.NET Framework) and PowerShell 7
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($b)
    $rng.Dispose()
    # Keep padding: Fernet keys are 44 chars WITH the trailing '=' (32-byte input);
    # stripping it makes the key invalid. '=' inside .env values is fine.
    return [Convert]::ToBase64String($b).Replace("+", "-").Replace("/", "_")
}

Write-Host "== GrowthCrew local deployment ==" -ForegroundColor Cyan

# 1. docker available?
try { docker info *> $null } catch {
    Write-Host "[ERROR] Docker is not running. Start Docker Desktop first, then re-run setup." -ForegroundColor Red
    exit 1
}

# 2. .env (keep existing one so secrets/data survive re-runs)
if (Test-Path ".env") {
    Write-Host "[1/4] .env already exists - keeping it (delete it to regenerate secrets)"
} else {
    Write-Host "[1/4] Generating .env with fresh random secrets ..."
    $jwt   = New-UrlSafeKey 48
    $fkey  = New-UrlSafeKey 32   # 32 bytes -> 44-char urlsafe, valid Fernet key
    $pgpwd = (New-UrlSafeKey 24).Substring(0, 24)
    $envContent = @"
GC_ENV=prod
GC_JWT_SECRET=$jwt
GC_ENCRYPTION_KEY=$fkey
GC_CORS_ORIGINS=["http://localhost:3211","http://127.0.0.1:3211"]
GC_ADMIN_USERNAMES=[]
POSTGRES_USER=growthcrew
POSTGRES_PASSWORD=$pgpwd
POSTGRES_DB=growthcrew
"@
    # ASCII only -> no BOM/encoding pitfalls
    [IO.File]::WriteAllText("$PSScriptRoot\.env", $envContent, [Text.Encoding]::ASCII)
    Write-Host "      .env written (never commit or zip it)"
}

# 3. build & start (db -> backend auto-migrates -> frontend)
Write-Host "[2/4] Building images and starting containers (first run takes a few minutes) ..."
# cmd /c wraps the 2>&1 redirect: PS 5.1 would otherwise turn docker's stderr
# progress output into a NativeCommandError and abort ($ErrorActionPreference=Stop)
$composeOut = cmd /c "docker compose up -d --build 2>&1" | Out-String
Write-Host $composeOut
if ($LASTEXITCODE -ne 0) {
    if ($composeOut -match "ports are not available|access permissions") {
        Write-Host "[HINT] A port is blocked by a Windows reserved range (common with Hyper-V/WSL)." -ForegroundColor Yellow
        Write-Host "       Fix: edit docker-compose.yml, change the LEFT number in the 'ports' section" -ForegroundColor Yellow
        Write-Host "       (e.g. 3211:3000 -> 3311:3000), sync GC_CORS_ORIGINS in .env, then re-run setup." -ForegroundColor Yellow
        Write-Host "       Check reserved ranges: netsh interface ipv4 show excludedportrange protocol=tcp" -ForegroundColor Yellow
    } else {
        Write-Host "[ERROR] compose failed. Logs: docker compose logs" -ForegroundColor Red
    }
    exit 1
}

# 4. wait for backend readiness (migration runs on first boot)
Write-Host "[3/4] Waiting for backend (first boot runs DB migrations) ..."
$ready = $false
foreach ($i in 1..60) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8100/api/v1/health/ready" -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 4 }
}
if (-not $ready) {
    Write-Host "[ERROR] Backend not ready after 4 min. Check: docker compose logs backend" -ForegroundColor Red
    exit 1
}

Write-Host "[4/4] All services are up." -ForegroundColor Green
Write-Host ""
Write-Host "  App (open in browser):   http://localhost:3211" -ForegroundColor Yellow
Write-Host "  Backend health:          http://localhost:8100/api/v1/health/ready"
Write-Host ""
Write-Host "  First time: register an account in the app, then set your model"
Write-Host "  (LLM) API key in Settings. See DEPLOY.md for details."
Write-Host ""
Write-Host "  Stop:  docker compose down      (data kept in docker volume)"
Write-Host "  Start again: docker compose up -d"
Write-Host "  Full reset:  docker compose down -v   (DELETES all data)"
