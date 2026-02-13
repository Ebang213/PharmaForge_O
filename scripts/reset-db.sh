#!/bin/bash
#
# reset-db.sh - Reset PharmaForge OS database (DESTROYS ALL DATA)
#
# This script removes all Docker volumes (including postgres_data),
# rebuilds images, and restarts the stack fresh.
#
# Use this when:
#   - POSTGRES_PASSWORD was changed and volume has old credentials
#   - Database is corrupted
#   - You need a fresh start for development
#
# WARNING: This will DELETE ALL DATA!
#
# Usage: ./scripts/reset-db.sh [-f|--force]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${RED}============================================${NC}"
echo -e "${RED}  PharmaForge OS - Database Reset Script   ${NC}"
echo -e "${RED}============================================${NC}"
echo ""
echo -e "${YELLOW}WARNING: This will DELETE ALL DATA including:${NC}"
echo "  - All users and organizations"
echo "  - All vendors, facilities, and alerts"
echo "  - All audit logs"
echo "  - The postgres_data volume"
echo ""

if [[ "$1" != "-f" && "$1" != "--force" ]]; then
    read -p "Are you sure? Type 'yes' to continue: " confirm
    if [[ "$confirm" != "yes" ]]; then
        echo -e "${YELLOW}Aborted.${NC}"
        exit 0
    fi
fi

cd "$PROJECT_ROOT"

echo ""
echo -e "${CYAN}[1/4] Stopping and removing containers + volumes...${NC}"
docker-compose -f docker-compose.prod.yml down -v

echo ""
echo -e "${CYAN}[2/4] Rebuilding images...${NC}"
docker-compose -f docker-compose.prod.yml build

echo ""
echo -e "${CYAN}[3/4] Starting services...${NC}"
docker-compose -f docker-compose.prod.yml up -d

echo ""
echo -e "${CYAN}[4/4] Waiting for services to become healthy (30s)...${NC}"
sleep 30

echo ""
echo -e "${GREEN}Container status:${NC}"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep pharmaforge

echo ""
echo -e "${GREEN}Recent API logs:${NC}"
docker logs pharmaforge_api --tail 20

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Database reset complete!                 ${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Ensure ADMIN_BOOTSTRAP_EMAIL and ADMIN_BOOTSTRAP_PASSWORD are set in .env"
echo "  2. Login with your bootstrap admin credentials"
echo "  3. Create additional users via /api/admin/users"
echo ""
