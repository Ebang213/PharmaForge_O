<#
.SYNOPSIS
    Reset PharmaForge OS database (DESTROYS ALL DATA)
    
.DESCRIPTION
    This script removes all Docker volumes (including postgres_data),
    rebuilds images, and restarts the stack fresh.
    
    Use this when:
    - POSTGRES_PASSWORD was changed and volume has old credentials
    - Database is corrupted
    - You need a fresh start for development
    
    WARNING: This will DELETE ALL DATA!
    
.EXAMPLE
    .\scripts\reset-db.ps1
#>

param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "============================================" -ForegroundColor Red
Write-Host "  PharmaForge OS - Database Reset Script   " -ForegroundColor Red
Write-Host "============================================" -ForegroundColor Red
Write-Host ""
Write-Host "WARNING: This will DELETE ALL DATA including:" -ForegroundColor Yellow
Write-Host "  - All users and organizations"
Write-Host "  - All vendors, facilities, and alerts"
Write-Host "  - All audit logs"
Write-Host "  - The postgres_data volume"
Write-Host ""

if (-not $Force) {
    $confirm = Read-Host "Are you sure? Type 'yes' to continue"
    if ($confirm -ne "yes") {
        Write-Host "Aborted." -ForegroundColor Yellow
        exit 0
    }
}

Write-Host ""
Write-Host "[1/4] Stopping and removing containers + volumes..." -ForegroundColor Cyan
Set-Location $ProjectRoot
docker-compose -f docker-compose.prod.yml down -v

Write-Host ""
Write-Host "[2/4] Rebuilding images..." -ForegroundColor Cyan
docker-compose -f docker-compose.prod.yml build

Write-Host ""
Write-Host "[3/4] Starting services..." -ForegroundColor Cyan
docker-compose -f docker-compose.prod.yml up -d

Write-Host ""
Write-Host "[4/4] Waiting for services to become healthy (30s)..." -ForegroundColor Cyan
Start-Sleep -Seconds 30

Write-Host ""
Write-Host "Container status:" -ForegroundColor Green
docker ps --format "table {{.Names}}\t{{.Status}}" | Select-String "pharmaforge"

Write-Host ""
Write-Host "Recent API logs:" -ForegroundColor Green
docker logs pharmaforge_api --tail 20

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Database reset complete!                 " -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Ensure ADMIN_BOOTSTRAP_EMAIL and ADMIN_BOOTSTRAP_PASSWORD are set in .env"
Write-Host "  2. Login with your bootstrap admin credentials"
Write-Host "  3. Create additional users via /api/admin/users"
Write-Host ""
