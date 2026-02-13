#!/bin/bash
# SSL Certificate Setup Helper for PharmaForge OS
set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

SSL_DIR="./nginx/ssl"
DOMAIN="${1:-}"

show_usage() {
    cat << EOF
${GREEN}SSL Certificate Setup for PharmaForge OS${NC}

Usage: $0 [OPTION]

Options:
    production DOMAIN    Set up Let's Encrypt certificates for production
    self-signed DOMAIN   Generate self-signed certificates for testing
    info                 Show current certificate information
    renew                  Renew Let's Encrypt certificates

Examples:
    $0 production pharmaforge.example.com
    $0 self-signed localhost
    $0 renew

EOF
}

check_certbot() {
    if ! command -v certbot &> /dev/null; then
        log_error "Certbot is not installed"
        log_info "Install with: sudo apt-get install certbot python3-certbot-nginx"
        exit 1
    fi
}

setup_production_ssl() {
    local domain="$1"
    
    log_step "Setting up Let's Encrypt SSL for: $domain"
    
    check_certbot
    
    log_info "Creating SSL directory..."
    mkdir -p "$SSL_DIR"
    
    log_warn "This will obtain a certificate from Let's Encrypt"
    log_warn "Make sure:"
    log_warn "  1. Your domain DNS points to this server"
    log_warn "  2. Ports 80 and 443 are accessible"
    log_warn "  3. No other service is using port 80"
    
    read -p "Continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cancelled"
        exit 0
    fi
    
    log_info "Stopping services on port 80..."
    docker-compose -f docker-compose.prod.yml down nginx || true
    
    log_info "Obtaining certificate..."
    sudo certbot certonly \
        --standalone \
        --preferred-challenges http \
        --email "admin@${domain}" \
        --agree-tos \
        --no-eff-email \
        -d "$domain" \
        -d "www.${domain}"
    
    log_info "Copying certificates..."
    sudo cp "/etc/letsencrypt/live/${domain}/fullchain.pem" "${SSL_DIR}/cert.pem"
    sudo cp "/etc/letsencrypt/live/${domain}/privkey.pem" "${SSL_DIR}/key.pem"
    sudo chmod 644 "${SSL_DIR}/cert.pem"
    sudo chmod 600 "${SSL_DIR}/key.pem"
    
    log_info "Setting up auto-renewal..."
    create_renewal_script "$domain"
    
    log_info "Starting services..."
    docker-compose -f docker-compose.prod.yml up -d
    
    log_info "✅ SSL certificate installed successfully!"
    log_info "Certificate expires in 90 days. Auto-renewal is configured."
    log_info ""
    log_info "Next steps:"
    log_info "  1. Update .env with CORS_ORIGINS=https://${domain}"
    log_info "  2. Uncomment SSL lines in nginx/nginx.conf"
    log_info "  3. Restart services: ./deploy.sh restart"
}

setup_self_signed() {
    local domain="$1"
    
    log_step "Generating self-signed certificate for: $domain"
    
    mkdir -p "$SSL_DIR"
    
    log_info "Creating certificate..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "${SSL_DIR}/key.pem" \
        -out "${SSL_DIR}/cert.pem" \
        -subj "/C=US/ST=State/L=City/O=Organization/OU=IT/CN=${domain}"
    
    chmod 644 "${SSL_DIR}/cert.pem"
    chmod 600 "${SSL_DIR}/key.pem"
    
    log_info "✅ Self-signed certificate created!"
    log_warn "⚠️  This is for TESTING ONLY - browsers will show security warnings"
    log_info ""
    log_info "Certificate location:"
    log_info "  Cert: ${SSL_DIR}/cert.pem"
    log_info "  Key:  ${SSL_DIR}/key.pem"
    log_info ""
    log_info "Next steps:"
    log_info "  1. Uncomment SSL lines in nginx/nginx.conf"
    log_info "  2. Restart services: ./deploy.sh restart"
}

show_certificate_info() {
    if [[ ! -f "${SSL_DIR}/cert.pem" ]]; then
        log_error "No certificate found at ${SSL_DIR}/cert.pem"
        exit 1
    fi
    
    log_info "Certificate Information:"
    echo ""
    openssl x509 -in "${SSL_DIR}/cert.pem" -text -noout | grep -E "Subject:|Issuer:|Not Before|Not After|DNS:"
    echo ""
    
    # Check expiration
    local expiry=$(openssl x509 -in "${SSL_DIR}/cert.pem" -noout -enddate | cut -d= -f2)
    local expiry_epoch=$(date -d "$expiry" +%s)
    local now_epoch=$(date +%s)
    local days_left=$(( ($expiry_epoch - $now_epoch) / 86400 ))
    
    if [[ $days_left -lt 30 ]]; then
        log_warn "Certificate expires in $days_left days!"
    else
        log_info "Certificate expires in $days_left days"
    fi
}

renew_certificates() {
    log_step "Renewing Let's Encrypt certificates..."
    
    check_certbot
    
    log_info "Stopping NGINX..."
    docker-compose -f docker-compose.prod.yml stop nginx
    
    log_info "Renewing..."
    sudo certbot renew --standalone
    
    log_info "Copying renewed certificates..."
    local domain=$(sudo certbot certificates | grep "Certificate Name:" | head -1 | awk '{print $3}')
    
    if [[ -n "$domain" ]]; then
        sudo cp "/etc/letsencrypt/live/${domain}/fullchain.pem" "${SSL_DIR}/cert.pem"
        sudo cp "/etc/letsencrypt/live/${domain}/privkey.pem" "${SSL_DIR}/key.pem"
        sudo chmod 644 "${SSL_DIR}/cert.pem"
        sudo chmod 600 "${SSL_DIR}/key.pem"
    fi
    
    log_info "Restarting NGINX..."
    docker-compose -f docker-compose.prod.yml start nginx
    
    log_info "✅ Certificates renewed successfully!"
}

create_renewal_script() {
    local domain="$1"
    local renewal_script="/etc/cron.monthly/renew-pharmaforge-ssl"
    
    sudo tee "$renewal_script" > /dev/null << 'EOF'
#!/bin/bash
# Auto-renewal script for PharmaForge OS SSL certificates

cd /path/to/PharmaForge_OS
./ssl-setup.sh renew

# Reload NGINX
docker-compose -f docker-compose.prod.yml exec nginx nginx -s reload
EOF
    
    sudo chmod +x "$renewal_script"
    
    log_info "Created auto-renewal script: $renewal_script"
    log_warn "⚠️  Update the path in $renewal_script to match your installation directory"
}

# Main script
case "${1:-}" in
    production)
        if [[ -z "${2:-}" ]]; then
            log_error "Domain required for production SSL"
            show_usage
            exit 1
        fi
        setup_production_ssl "$2"
        ;;
    self-signed)
        if [[ -z "${2:-}" ]]; then
            log_error "Domain required for self-signed certificate"
            show_usage
            exit 1
        fi
        setup_self_signed "$2"
        ;;
    info)
        show_certificate_info
        ;;
    renew)
        renew_certificates
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
