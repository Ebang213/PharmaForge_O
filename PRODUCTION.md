# PharmaForge OS - Production Deployment Guide

## 🏭 Production Architecture

```
┌─────────────────────────────────────────────────┐
│           NGINX (Port 80/443)                   │
│        ✓ SSL Termination                        │
│        ✓ Static File Serving                    │
│        ✓ Rate Limiting                          │
│        ✓ Security Headers                       │
└──────────────────┬──────────────────────────────┘
                   │
      ┌────────────┼────────────┐
      │            │            │
   /api/*       /*          WebSocket
      │            │            │
      ▼            ▼            ▼
┌──────────┐  ┌─────────┐  ┌─────────┐
│   API    │  │ React   │  │ Worker  │
│ Gunicorn │  │  SPA    │  │   RQ    │
│ 4 workers│  │ Static  │  │  Queue  │
└─────┬────┘  └─────────┘  └────┬────┘
      │                          │
      └──────────┬───────────────┘
                 │
    ┌────────────┼────────────┐
    │            │            │
┌───▼───┐   ┌───▼───┐   ┌───▼────┐
│Postgres│   │ Redis │   │ Qdrant │
│  DB    │   │ Cache │   │ Vector │
└────────┘   └───────┘   └────────┘
  (Internal Network - No External Access)
```

## 🚀 Quick Start - Production Deployment

### Prerequisites
- Docker 20.10+
- Docker Compose 2.0+
- 4GB+ RAM
- 20GB+ Disk Space

### 1. Initial Setup

```bash
# Clone the repository
git clone <repository-url>
cd PharmaForge_OS

# Copy environment template
cp .env.production .env

# Edit .env with production values
# IMPORTANT: Change all CHANGE_THIS values!
nano .env
```

### 2. Configure Environment Variables

**Critical Variables** (Must be changed):
```bash
SECRET_KEY=<generate-random-64-char-string>
POSTGRES_PASSWORD=<strong-database-password>
REDIS_PASSWORD=<strong-redis-password>
```

Generate secure values:
```bash
# Generate SECRET_KEY (Linux/Mac)
openssl rand -hex 32

# Generate passwords
openssl rand -base64 32
```

### 3. Deploy

**Linux/Mac:**
```bash
chmod +x deploy.sh
./deploy.sh deploy
```

**Windows:**
```powershell
.\deploy.ps1 deploy
```

### 4. Run Database Migrations (First Deploy Only)

After containers are running, initialize the database schema:

```powershell
# Run Alembic migrations
docker exec pharmaforge_api sh -c "cd /code && alembic upgrade head"

# Restart API to trigger admin bootstrap
docker-compose -f docker-compose.prod.yml restart api worker
```

### 5. Access Application

- **URL**: http://localhost (or your domain)
- **Login**: Use the credentials from your `.env` file:
  - `ADMIN_BOOTSTRAP_EMAIL`
  - `ADMIN_BOOTSTRAP_PASSWORD`

⚠️ **IMPORTANT**: 
- Set `ADMIN_BOOTSTRAP_EMAIL` and `ADMIN_BOOTSTRAP_PASSWORD` in `.env` **before first startup**
- The bootstrap admin is only created when the database is empty
- Change the password immediately after first login!
- For user management after setup, go to **Admin → Users** in the UI


## 📋 Deployment Commands

### Windows (PowerShell)
```powershell
.\deploy.ps1 deploy           # Full deployment
.\deploy.ps1 update           # Update deployment
.\deploy.ps1 start            # Start services
.\deploy.ps1 stop             # Stop services
.\deploy.ps1 restart          # Restart services
.\deploy.ps1 status           # Show status
.\deploy.ps1 logs api         # View API logs
.\deploy.ps1 backup           # Backup database
.\deploy.ps1 health           # Health check
```

### Linux/Mac (Bash)
```bash
./deploy.sh deploy            # Full deployment
./deploy.sh update            # Update deployment
./deploy.sh start             # Start services
./deploy.sh stop              # Stop services
./deploy.sh restart           # Restart services
./deploy.sh status            # Show status
./deploy.sh logs api          # View API logs
./deploy.sh backup            # Backup database
./deploy.sh health            # Health check
```

## 🔐 Security Hardening

### 1. SSL/TLS Configuration

For production, enable HTTPS:

1. Obtain SSL certificates (Let's Encrypt recommended):
```bash
# Using certbot
sudo certbot certonly --standalone -d yourdomain.com
```

2. Copy certificates:
```bash
mkdir -p nginx/ssl
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem nginx/ssl/cert.pem
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem nginx/ssl/key.pem
```

3. Update `nginx/nginx.conf`:
   - Uncomment SSL lines (search for `# Enable for production with SSL`)
   - Update `server_name` to your domain

4. Update `.env`:
```bash
HTTPS_PORT=443
CORS_ORIGINS=https://yourdomain.com
```

### 2. Firewall Configuration

```bash
# Allow only HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Block direct database access
sudo ufw deny 5432/tcp
sudo ufw deny 6379/tcp
sudo ufw deny 6333/tcp
```

### 3. Change Default Credentials

1. Login with default credentials
2. Go to Settings → Change Password
3. Create new admin user with strong password
4. Delete or disable default `admin@acmepharma.com` account

### 4. Environment Hardening

```bash
# Set restrictive permissions on .env
chmod 600 .env

# Never commit .env to git
echo ".env" >> .gitignore
```

## 📊 Monitoring & Logging

### View Logs

```bash
# All services
docker-compose -f docker-compose.prod.yml logs -f

# Specific service
docker-compose -f docker-compose.prod.yml logs -f api
docker-compose -f docker-compose.prod.yml logs -f nginx
docker-compose -f docker-compose.prod.yml logs -f worker

# With timestamps
docker-compose -f docker-compose.prod.yml logs -f --timestamps api
```

### Health Checks

```bash
# Application health
curl http://localhost/health

# API health
curl http://localhost/api/health

# Database health  
docker-compose -f docker-compose.prod.yml exec postgres pg_isready
```

### Performance Monitoring

```bash
# Container stats
docker stats

# Disk usage
docker system df

# Service resource usage
docker-compose -f docker-compose.prod.yml ps
```

## 💾 Backup & Recovery

### Automated Backups

```bash
# Manual backup
./deploy.sh backup    # Linux/Mac
.\deploy.ps1 backup   # Windows

# Automated daily backups (Linux cron)
0 2 * * * /path/to/deploy.sh backup
```

### Restore from Backup

```bash
# Stop services
docker-compose -f docker-compose.prod.yml down

# Restore database
gunzip -c backups/pharmaforge_db_YYYYMMDD_HHMMSS.sql.gz | \
  docker-compose -f docker-compose.prod.yml run --rm -T postgres \
  psql -U pharmaforge pharmaforge

# Restart services
docker-compose -f docker-compose.prod.yml up -d
```

## 🔄 Updates & Maintenance

### Application Updates

```bash
# 1. Pull latest code
git pull origin main

# 2. Run update deployment (includes backup)
./deploy.sh update    # Linux/Mac
.\deploy.ps1 update   # Windows
```

### Database Migrations

```bash
# View migration status
docker-compose -f docker-compose.prod.yml exec api alembic current

# Run migrations
docker-compose -f docker-compose.prod.yml exec api alembic upgrade head

# Rollback one version
docker-compose -f docker-compose.prod.yml exec api alembic downgrade -1
```

### Scaling

Scale API workers:
```bash
docker-compose -f docker-compose.prod.yml up -d --scale api=3
```

## 🐛 Troubleshooting

### Services Won't Start

```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs

# Check disk space
df -h

# Check for port conflicts
netstat -tuln | grep -E '80|443|5432|6379|6333'
```

### Database Connection Issues

#### 🔴 "Password authentication failed" (Credential Drift)

**Problem:** You changed `POSTGRES_PASSWORD` in `.env` but the existing `postgres_data` volume still has the old credentials.

**Important:** PostgreSQL stores user credentials **inside the data volume** at first startup. Changing `.env` does NOT update existing volumes.

**Fix (Development - destroys data):**
```powershell
# Use the reset script
.\scripts\reset-db.ps1

# Or manually:
docker-compose -f docker-compose.prod.yml down -v
docker-compose -f docker-compose.prod.yml up -d --build
```

**Fix (Production - preserves data):**
```powershell
# Use the password rotation script
.\scripts\rotate-db-password.ps1

# Or manually run ALTER USER:
docker exec pharmaforge_postgres psql -U postgres -c "ALTER USER pharmaforge WITH PASSWORD 'your-new-password';"
docker-compose -f docker-compose.prod.yml restart api worker
```

#### General Connection Issues

```bash
# Check Postgres health
docker-compose -f docker-compose.prod.yml exec postgres pg_isready

# View Postgres logs
docker-compose -f docker-compose.prod.yml logs postgres
```


### Frontend Not Loading

```bash
# Rebuild frontend
cd frontend
npm run build
cd ..

# Rebuild nginx
docker-compose -f docker-compose.prod.yml build nginx
docker-compose -f docker-compose.prod.yml up -d nginx
```

### Memory Issues

```bash
# Check memory usage
free -h

# Restart services
docker-compose -f docker-compose.prod.yml restart

# Prune unused Docker resources
docker system prune -a
```

## 📈 Performance Optimization

### Database

```sql
-- Create indexes (run in Postgres container)
CREATE INDEX CONCURRENTLY idx_vendors_org_id ON vendors(organization_id);
CREATE INDEX CONCURRENTLY idx_audit_logs_timestamp ON audit_logs(timestamp);
```

### Redis

```bash
# Monitor Redis performance
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO stats
```

### NGINX

Edit `nginx/nginx.conf` for optimization:
- Adjust `worker_processes` based on CPU cores
- Tune `worker_connections`
- Configure `client_max_body_size` for your needs

## 🔒 Security Best Practices

1. **Network Isolation**: All internal services in private network
2. **Rate Limiting**: API endpoints protected from abuse
3. **HTTPS Only**: Force SSL in production
4. **Strong Passwords**: Use generated passwords
5. **Regular Updates**: Keep Docker images updated
6. **Audit Logs**: Monitor all user actions
7. **Backup Strategy**: Daily automated backups
8. **Access Control**: Implement RBAC properly
9. **Environment Variables**: Never commit secrets
10. **Monitoring**: Set up alerts for errors

## 📞 Support

For issues or questions:
- Check logs: `./deploy.sh logs`
- Review troubleshooting section above
- Check GitHub issues
- Contact support team

## 📄 License

MIT License - See LICENSE file for details
