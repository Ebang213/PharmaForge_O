<#
.SYNOPSIS
    Rotate database password for existing PostgreSQL volume
    
.DESCRIPTION
    This script updates the PostgreSQL user password to match the 
    POSTGRES_PASSWORD in your .env file, WITHOUT destroying data.
    
    Use this when:
    - You get "password authentication failed" errors
    - You changed POSTGRES_PASSWORD but have existing data
    - You need to sync credentials between .env and the running DB
    
    This is SAFER than reset-db.ps1 because it preserves data.
    
.EXAMPLE
    .\scripts\rotate-db-password.ps1
    
.NOTES
    Requires the postgres container to be running.
    Uses the 'postgres' superuser which has no password by default.
#>

param(
    [string]$EnvFile = ".env"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  PharmaForge OS - DB Password Rotation    " -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Change to project root
Set-Location $ProjectRoot

# Load .env file
if (-not (Test-Path $EnvFile)) {
    Write-Host "ERROR: $EnvFile not found!" -ForegroundColor Red
    Write-Host "Create a .env file with POSTGRES_USER and POSTGRES_PASSWORD" -ForegroundColor Yellow
    exit 1
}

# Parse .env file
$envContent = Get-Content $EnvFile | Where-Object { $_ -match '=' -and $_ -notmatch '^\s*#' }
$envVars = @{}
foreach ($line in $envContent) {
    $parts = $line -split '=', 2
    if ($parts.Count -eq 2) {
        $envVars[$parts[0].Trim()] = $parts[1].Trim()
    }
}

$pgUser = $envVars["POSTGRES_USER"]
$pgPassword = $envVars["POSTGRES_PASSWORD"]

if (-not $pgUser) { $pgUser = "pharmaforge" }
if (-not $pgPassword) {
    Write-Host "ERROR: POSTGRES_PASSWORD not found in $EnvFile" -ForegroundColor Red
    exit 1
}

Write-Host "Target user: $pgUser" -ForegroundColor Yellow
Write-Host "New password: ******* (from $EnvFile)" -ForegroundColor Yellow
Write-Host ""

# Check if postgres container is running
$pgContainer = docker ps --filter "name=pharmaforge_postgres" --format "{{.Names}}"
if (-not $pgContainer) {
    Write-Host "ERROR: pharmaforge_postgres container is not running!" -ForegroundColor Red
    Write-Host "Start the stack first: docker-compose -f docker-compose.prod.yml up -d" -ForegroundColor Yellow
    exit 1
}

Write-Host "[1/3] Updating PostgreSQL user password..." -ForegroundColor Cyan

# Execute ALTER USER inside the postgres container
# Using psql -U postgres (superuser has no password by default in the container)
$alterCmd = "ALTER USER `"$pgUser`" WITH PASSWORD '$pgPassword';"
docker exec pharmaforge_postgres psql -U postgres -c $alterCmd

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to update password!" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Password updated in PostgreSQL" -ForegroundColor Green
Write-Host ""

Write-Host "[2/3] Restarting API and Worker containers..." -ForegroundColor Cyan
docker-compose -f docker-compose.prod.yml restart api worker

Write-Host ""
Write-Host "[3/3] Waiting for services to restart (15s)..." -ForegroundColor Cyan
Start-Sleep -Seconds 15

Write-Host ""
Write-Host "Container status:" -ForegroundColor Green
docker ps --format "table {{.Names}}\t{{.Status}}" | Select-String "pharmaforge"

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Password rotation complete!              " -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "The database password has been updated to match your .env file." -ForegroundColor Yellow
Write-Host "Your existing data has been preserved." -ForegroundColor Yellow
Write-Host ""
Write-Host "Test the connection:" -ForegroundColor Yellow
Write-Host "  Invoke-RestMethod http://localhost/api/health" -ForegroundColor White
Write-Host ""
