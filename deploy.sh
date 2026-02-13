#!/bin/bash
# PharmaForge OS - Production Deployment Script
set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env"
BACKUP_DIR="./backups"

# ============================================
# Helper Functions
# ============================================
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    log_info "Prerequisites check passed ✓"
}

check_environment() {
    log_info "Checking environment configuration..."
    
    if [ ! -f "$ENV_FILE" ]; then
        log_error ".env file not found. Copy .env.production to .env and configure it."
        exit 1
    fi
    
    # Check required variables
    source "$ENV_FILE"
    
    if [ "${SECRET_KEY:-}" == "CHANGE_THIS_TO_RANDOM_64_CHAR_STRING_IN_PRODUCTION" ]; then
        log_error "SECRET_KEY not configured in .env file"
        exit 1
    fi
    
    if [ "${POSTGRES_PASSWORD:-}" == "CHANGE_THIS_STRONG_PASSWORD" ]; then
        log_error "POSTGRES_PASSWORD not configured in .env file"
        exit 1
    fi
    
    if [ "${REDIS_PASSWORD:-}" == "CHANGE_THIS_REDIS_PASSWORD" ]; then
        log_error "REDIS_PASSWORD not configured in .env file"
        exit 1
    fi
    
    log_info "Environment configuration valid ✓"
}

build_frontend() {
    log_info "Building frontend for production..."
    
    cd frontend
    
    if [ ! -d "node_modules" ]; then
        log_info "Installing frontend dependencies..."
        npm ci
    fi
    
    log_info "Building optimized production bundle..."
    npm run build
    
    if [ ! -d "dist" ]; then
        log_error "Frontend build failed - dist directory not created"
        exit 1
    fi
    
    cd ..
    log_info "Frontend build completed ✓"
}

build_images() {
    log_info "Building Docker images..."
    
    docker-compose -f "$COMPOSE_FILE" build --no-cache
    
    log_info "Docker images built ✓"
}

run_migrations() {
    log_info "Running database migrations..."
    
    docker-compose -f "$COMPOSE_FILE" run --rm api alembic upgrade head
    
    log_info "Migrations completed ✓"
}

start_services() {
    log_info "Starting services..."
    
    docker-compose -f "$COMPOSE_FILE" up -d
    
    log_info "Services started ✓"
}

health_check() {
    log_info "Performing health checks..."
    
    local max_attempts=30
    local attempt=1
    
    while [ $attempt -le $max_attempts ]; do
        if curl -f -s http://localhost/health > /dev/null; then
            log_info "Health check passed ✓"
            return 0
        fi
        
        log_warn "Health check attempt $attempt/$max_attempts failed, retrying..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    log_error "Health check failed after $max_attempts attempts"
    return 1
}

show_status() {
    log_info "Service Status:"
    docker-compose -f "$COMPOSE_FILE" ps
    
    echo ""
    log_info "Container Logs (last 20 lines):"
    docker-compose -f "$COMPOSE_FILE" logs --tail=20
}

backup_database() {
    log_info "Creating database backup..."
    
    mkdir -p "$BACKUP_DIR"
    
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="$BACKUP_DIR/pharmaforge_db_${timestamp}.sql"
    
    source "$ENV_FILE"
    docker-compose -f "$COMPOSE_FILE" exec -T postgres pg_dump \
        -U "${POSTGRES_USER}" \
        "${POSTGRES_DB}" > "$backup_file"
    
    gzip "$backup_file"
    
    log_info "Database backup created: ${backup_file}.gz ✓"
}

# ============================================
# Main Deployment Commands
# ============================================
deploy_full() {
    log_info "Starting full deployment..."
    
    check_prerequisites
    check_environment
    build_frontend
    build_images
    start_services
    sleep 10
    run_migrations
    health_check
    
    log_info "Deployment completed successfully! ✓"
    log_info "Application is now running at http://localhost"
    log_info ""
    log_info "Default credentials:"
    log_info "  Email: admin@acmepharma.com"
    log_info "  Password: admin123"
    log_info ""
    log_info "⚠️  Remember to change the default password immediately!"
}

deploy_update() {
    log_info "Starting update deployment..."
    
    backup_database
    build_frontend
    build_images
    
    log_info "Stopping services..."
    docker-compose -f "$COMPOSE_FILE" down
    
    start_services
    sleep 10
    run_migrations
    health_check
    
    log_info "Update deployment completed ✓"
}

stop_services() {
    log_info "Stopping all services..."
    docker-compose -f "$COMPOSE_FILE" down
    log_info "Services stopped ✓"
}

start_services_only() {
    log_info "Starting services..."
    docker-compose -f "$COMPOSE_FILE" up -d
    log_info "Services started ✓"
}

restart_services() {
    log_info "Restarting services..."
    docker-compose -f "$COMPOSE_FILE" restart
    log_info "Services restarted ✓"
}

view_logs() {
    local service="${1:-}"
    if [ -z "$service" ]; then
        docker-compose -f "$COMPOSE_FILE" logs -f
    else
        docker-compose -f "$COMPOSE_FILE" logs -f "$service"
    fi
}

# ============================================
# Command Line Interface
# ============================================
show_usage() {
    cat << EOF
PharmaForge OS - Production Deployment Tool

Usage: $0 [COMMAND]

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
    $0 deploy                 # Initial deployment
    $0 update                 # Update existing deployment
    $0 logs api               # View API logs
    $0 backup                 # Create database backup

EOF
}

# ============================================
# Main Script
# ============================================
case "${1:-}" in
    deploy)
        deploy_full
        ;;
    update)
        deploy_update
        ;;
    start)
        start_services_only
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    status)
        show_status
        ;;
    logs)
        view_logs "${2:-}"
        ;;
    backup)
        backup_database
        ;;
    health)
        health_check
        ;;
    build-frontend)
        build_frontend
        ;;
    build-images)
        build_images
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
