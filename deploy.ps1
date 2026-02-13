# PharmaForge OS - Production Deployment Script (Windows)
param(
    [Parameter(Position=0)]
    [ValidateSet('deploy', 'update', 'start', 'stop', 'restart', 'status', 'logs', 'backup', 'health', 'build-frontend', 'build-images')]
    [string]$Command,
    
    [Parameter(Position=1)]
    [string]$Service
)

$ErrorActionPreference = "Stop"

# Configuration
$ComposeFile = "docker-compose.prod.yml"
$EnvFile = ".env"
$BackupDir = ".\backups"

# ============================================
# Helper Functions
# ============================================
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Error-Custom {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Check-Prerequisites {
    Write-Info "Checking prerequisites..."
    
    if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Error-Custom "Docker is not installed"
        exit 1
    }
    
    if (!(Get-Command docker-compose -ErrorAction SilentlyContinue)) {
        Write-Error-Custom "Docker Compose is not installed"
        exit 1
    }
    
    Write-Info "Prerequisites check passed ✓"
}

function Check-Environment {
    Write-Info "Checking environment configuration..."
    
    if (!(Test-Path $EnvFile)) {
        Write-Error-Custom ".env file not found. Copy .env.production to .env and configure it."
        exit 1
    }
    
    # Read .env file
    $envContent = Get-Content $EnvFile | Where-Object { $_ -notmatch '^\s*#' -and $_ -match '=' }
    $envVars = @{}
    foreach ($line in $envContent) {
        $parts = $line -split '=', 2
        if ($parts.Count -eq 2) {
            $envVars[$parts[0].Trim()] = $parts[1].Trim()
        }
    }
    
    # Check required variables
    if ($envVars['SECRET_KEY'] -eq 'CHANGE_THIS_TO_RANDOM_64_CHAR_STRING_IN_PRODUCTION') {
        Write-Error-Custom "SECRET_KEY not configured in .env file"
        exit 1
    }
    
    if ($envVars['POSTGRES_PASSWORD'] -eq 'CHANGE_THIS_STRONG_PASSWORD') {
        Write-Error-Custom "POSTGRES_PASSWORD not configured in .env file"
        exit 1
    }
    
    if ($envVars['REDIS_PASSWORD'] -eq 'CHANGE_THIS_REDIS_PASSWORD') {
        Write-Error-Custom "REDIS_PASSWORD not configured in .env file"
        exit 1
    }
    
    Write-Info "Environment configuration valid ✓"
}

function Build-Frontend {
    Write-Info "Building frontend for production..."
    
    Push-Location frontend
    
    if (!(Test-Path "node_modules")) {
        Write-Info "Installing frontend dependencies..."
        npm ci
    }
    
    Write-Info "Building optimized production bundle..."
    npm run build
    
    if (!(Test-Path "dist")) {
        Write-Error-Custom "Frontend build failed - dist directory not created"
        Pop-Location
        exit 1
    }
    
    Pop-Location
    Write-Info "Frontend build completed ✓"
}

function Build-Images {
    Write-Info "Building Docker images..."
    
    docker-compose -f $ComposeFile build --no-cache
    
    Write-Info "Docker images built ✓"
}

function Run-Migrations {
    Write-Info "Running database migrations..."
    
    docker-compose -f $ComposeFile run --rm api alembic upgrade head
    
    Write-Info "Migrations completed ✓"
}

function Start-Services {
    Write-Info "Starting services..."
    
    docker-compose -f $ComposeFile up -d
    
    Write-Info "Services started ✓"
}

function Health-Check {
    Write-Info "Performing health checks..."
    
    $maxAttempts = 30
    $attempt = 1
    
    while ($attempt -le $maxAttempts) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost/health" -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                Write-Info "Health check passed ✓"
                return $true
            }
        }
        catch {
            Write-Warn "Health check attempt $attempt/$maxAttempts failed, retrying..."
            Start-Sleep -Seconds 2
        }
        $attempt++
    }
    
    Write-Error-Custom "Health check failed after $maxAttempts attempts"
    return $false
}

function Show-Status {
    Write-Info "Service Status:"
    docker-compose -f $ComposeFile ps
    
    Write-Host ""
    Write-Info "Container Logs (last 20 lines):"
    docker-compose -f $ComposeFile logs --tail=20
}

function Backup-Database {
    Write-Info "Creating database backup..."
    
    if (!(Test-Path $BackupDir)) {
        New-Item -ItemType Directory -Path $BackupDir | Out-Null
    }
    
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $backupFile = Join-Path $BackupDir "pharmaforge_db_$timestamp.sql"
    
    # Read environment
    $envContent = Get-Content $EnvFile | Where-Object { $_ -notmatch '^\s*#' -and $_ -match '=' }
    $envVars = @{}
    foreach ($line in $envContent) {
        $parts = $line -split '=', 2
        if ($parts.Count -eq 2) {
            $envVars[$parts[0].Trim()] = $parts[1].Trim()
        }
    }
    
    $postgresUser = $envVars['POSTGRES_USER']
    $postgresDb = $envVars['POSTGRES_DB']
    
    docker-compose -f $ComposeFile exec -T postgres pg_dump -U $postgresUser $postgresDb | Out-File -Encoding UTF8 $backupFile
    
    # Compress the backup
    Compress-Archive -Path $backupFile -DestinationPath "$backupFile.zip" -Force
    Remove-Item $backupFile
    
    Write-Info "Database backup created: $backupFile.zip ✓"
}

# ============================================
# Main Deployment Commands
# ============================================
function Deploy-Full {
    Write-Info "Starting full deployment..."
    
    Check-Prerequisites
    Check-Environment
    Build-Frontend
    Build-Images
    Start-Services
    Start-Sleep -Seconds 10
    Run-Migrations
    
    if (Health-Check) {
        Write-Info "Deployment completed successfully! ✓"
        Write-Info "Application is now running at http://localhost"
        Write-Host ""
        Write-Info "Default credentials:"
        Write-Info "  Email: admin@acmepharma.com"
        Write-Info "  Password: admin123"
        Write-Host ""
        Write-Warn "⚠️  Remember to change the default password immediately!"
    }
    else {
        Write-Error-Custom "Deployment health check failed"
        exit 1
    }
}

function Deploy-Update {
    Write-Info "Starting update deployment..."
    
    Backup-Database
    Build-Frontend
    Build-Images
    
    Write-Info "Stopping services..."
    docker-compose -f $ComposeFile down
    
    Start-Services
    Start-Sleep -Seconds 10
    Run-Migrations
    
    if (Health-Check) {
        Write-Info "Update deployment completed ✓"
    }
    else {
        Write-Error-Custom "Update deployment health check failed"
        exit 1
    }
}

function Stop-Services {
    Write-Info "Stopping all services..."
    docker-compose -f $ComposeFile down
    Write-Info "Services stopped ✓"
}

function Start-ServicesOnly {
    Write-Info "Starting services..."
    docker-compose -f $ComposeFile up -d
    Write-Info "Services started ✓"
}

function Restart-Services {
    Write-Info "Restarting services..."
    docker-compose -f $ComposeFile restart
    Write-Info "Services restarted ✓"
}

function View-Logs {
    param([string]$ServiceName)
    
    if ($ServiceName) {
        docker-compose -f $ComposeFile logs -f $ServiceName
    }
    else {
        docker-compose -f $ComposeFile logs -f
    }
}

function Show-Usage {
    Write-Host @"
PharmaForge OS - Production Deployment Tool

Usage: .\deploy.ps1 [COMMAND] [OPTIONS]

Commands:
    deploy          Full deployment (build + start + migrate)
    update          Update deployment (backup + rebuild + restart + migrate)
    start           Start all services
    stop            Stop all services
    restart         Restart all services
    status          Show service status
    logs [service]  View logs (optional: specific service)
    backup          Create database backup
    health          Run health check
    build-frontend  Build frontend only
    build-images    Build Docker images only
    
Examples:
    .\deploy.ps1 deploy                 # Initial deployment
    .\deploy.ps1 update                 # Update existing deployment
    .\deploy.ps1 logs api               # View API logs
    .\deploy.ps1 backup                 # Create database backup

"@
}

# ============================================
# Main Script
# ============================================
switch ($Command) {
    'deploy' { Deploy-Full }
    'update' { Deploy-Update }
    'start' { Start-ServicesOnly }
    'stop' { Stop-Services }
    'restart' { Restart-Services }
    'status' { Show-Status }
    'logs' { View-Logs -ServiceName $Service }
    'backup' { Backup-Database }
    'health' { Health-Check }
    'build-frontend' { Build-Frontend }
    'build-images' { Build-Images }
    default { Show-Usage; exit 1 }
}
