# ⚡ Quick Start Guide

## 🎯 Choose Your Path

### 🏭 I want to deploy for PRODUCTION use
**→ Go to [Production Deployment](#production-deployment)**

### 💻 I want to develop/test locally
**→ Go to [Development Setup](#development-setup)**

---

## 🏭 Production Deployment

**Time**: ~10 minutes  
**Difficulty**: Easy  
**Result**: Production-ready system on port 80/443

### Step 1: Prerequisites ✓

```bash
# Check Docker
docker --version  # Need 20.10+

# Check Docker Compose
docker-compose --version  # Need 2.0+
```

### Step 2: Get the Code 📥

```bash
git clone <repository-url>
cd PharmaForge_OS
```

### Step 3:Configure Secrets 🔐

```bash
# Copy template
cp .env.production .env

# Generate secrets (Linux/Mac)
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32)" >> .env
echo "REDIS_PASSWORD=$(openssl rand -base64 32)" >> .env

# Windows PowerShell
Add-Content .env "SECRET_KEY=$([Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)))"
```

**Or manually edit `.env`** and change:
- `SECRET_KEY=CHANGE_THIS...` → Random 64-char string
- `POSTGRES_PASSWORD=CHANGE_THIS...` → Strong password
- `REDIS_PASSWORD=CHANGE_THIS...` → Strong password

### Step 4: Deploy 🚀

**Linux/Mac:**
```bash
chmod +x deploy.sh
./deploy.sh deploy
```

**Windows:**
```powershell
.\deploy.ps1 deploy
```

### Step 5: Access & Login 🎉

1. Open browser: **http://localhost**
2. Login:
   - Email: `admin@acmepharma.com`
   - Password: `admin123`
3. **⚠️ IMMEDIATELY change password** in Settings!

### Step 6: Next Steps 📋

- [ ] Change default password
- [ ] Create real user accounts
- [ ] Upload documents to Copilot
- [ ] Configure vendors
- [ ] Set up SSL (see [SSL Setup](#ssl-setup))

---

## 💻 Development Setup

**Time**: ~5 minutes  
**Difficulty**: Very Easy  
**Result**: Hot-reload development environment

### Step 1: Get the Code 📥

```bash
git clone <repository-url>
cd PharmaForge_OS
```

### Step 2: Configure Environment 🔧

```bash
# Copy development template
cp .env.example .env

# No changes needed for development!
```

### Step 3: Start Services 🚀

```bash
docker-compose up --build
```

Wait for:
```
✔ Container pharmaforge_postgres   Healthy
✔ Container pharmaforge_redis      Healthy
✔ Container pharmaforge_api        Started
✔ Container pharmaforge_frontend   Started
✔ Container pharmaforge_worker     Started
```

### Step 4: Seed Demo Data 🌱

```bash
# In a new terminal
docker-compose exec api python -m app.db.seed
```

### Step 5: Access Development Servers 🎉

- **Frontend**: http://localhost:5173 ← Main app with hot-reload
- **API**: http://localhost:8001
- **API Docs**: http://localhost:8001/docs ← Interactive API docs

**Login:**
- Email: `admin@acmepharma.com`
- Password: `admin123`

### Development Workflow 🛠️

```bash
# View logs
docker-compose logs -f

# Restart a service
docker-compose restart api

# Stop all
docker-compose down

# Rebuild after code changes
docker-compose up --build
```

---

## 🔐 SSL Setup (Production Only)

### Option A: Let's Encrypt (Production)

```bash
chmod +x ssl-setup.sh
./ssl-setup.sh production yourdomain.com
```

**Requirements:**
- Domain pointing to your server
- Ports 80 & 443 accessible
- Valid email

### Option B: Self-Signed (Testing)

```bash
./ssl-setup.sh self-signed localhost
```

**Note:** Browsers will show warnings (this is normal for testing)

### After SSL Setup

1. Uncomment SSL lines in `nginx/nginx.conf`
2. Update `.env`: `CORS_ORIGINS=https://yourdomain.com`
3. Restart: `./deploy.sh restart`

---

## 📊 Verification Checklist

### Production ✅

```bash
# Health check
curl http://localhost/health
# Expected: {"status":"healthy", ...}

# API check
curl http://localhost/api/health
# Expected: {"status":"healthy", ...}

# View services
./deploy.sh status

# Test login
# Go to http://localhost and login
```

### Development ✅

```bash
# Frontend check
curl http://localhost:5173
# Expected: HTML response

# API check
curl http://localhost:8001/api/health
# Expected: {"status":"healthy", ...}

# API docs (in browser)
# Go to http://localhost:8001/docs
```

---

## 🐛 Common Issues & Fixes

### Issue: Port already in use

```bash
# Check what's using the port
netstat -tuln | grep ":80"

# Change port in .env
HTTP_PORT=8080

# Restart
./deploy.sh restart
```

### Issue: Database connection failed

```bash
# Check PostgreSQL
./deploy.sh logs postgres

# Check password in .env matches
cat .env | grep POSTGRES_PASSWORD

# Restart database
docker-compose -f docker-compose.prod.yml restart postgres
```

### Issue: Frontend shows "Cannot connect to server"

```bash
# Check API is running
./deploy.sh status

# Check API logs
./deploy.sh logs api

# Try health check
curl http://localhost/api/health
```

### Issue: Permission denied on deploy scripts

```bash
chmod +x deploy.sh
chmod +x ssl-setup.sh
```

---

## 📞 Getting Help

### 1. Check Documentation
- [Production Guide](./PRODUCTION.md) - Full production docs
- [Hardening Summary](./HARDENING_SUMMARY.md) - What changed
- [README](./README.md) - Complete overview

### 2. View Logs
```bash
./deploy.sh logs              # All services
./deploy.sh logs api          # Just API
./deploy.sh logs nginx        # Just NGINX
```

### 3. Health Checks
```bash
./deploy.sh health            # Run health checks
./deploy.sh status            # Service status
docker ps                     # Container status
```

### 4. Still Stuck?
- Check GitHub Issues
- Review troubleshooting in [PRODUCTION.md](./PRODUCTION.md)
- Contact support team

---

## 🎓 Next Steps After Setup

### For Production Users
1. **Security**
   - [ ] Change default password
   - [ ] Set up SSL/HTTPS
   - [ ] Configure firewall
   - [ ] Review security checklist in PRODUCTION.md

2. **Configuration**
   - [ ] Set up LLM provider (OpenAI/Anthropic)
   - [ ] Configure email notifications
   - [ ] Set up automated backups
   - [ ] Configure monitoring

3. **Operations**
   - [ ] Create user accounts
   - [ ] Import vendor data
   - [ ] Upload regulatory documents
   - [ ] Test backup/restore

### For Developers
1. **Explore**
   - [ ] Browse API docs at http://localhost:8001/docs
   - [ ] Test all features
   - [ ] Upload sample files

2. **Customize**
   - [ ] Modify frontend in `frontend/src`
   - [ ] Add API endpoints in `app/api`
   - [ ] Create new database models in `app/db/models.py`

3. **Test**
   - [ ] Write unit tests
   - [ ] Run `pytest`
   - [ ] Test in production mode locally

---

## 📚 Documentation Index

| Document | Purpose |
|----------|---------|
| [QUICKSTART.md](./QUICKSTART.md) | This file - fastest path to running system |
| [README.md](./README.md) | Complete project overview |
| [PRODUCTION.md](./PRODUCTION.md) | Production deployment & operations |
| [HARDENING_SUMMARY.md](./HARDENING_SUMMARY.md) | Production changes explained |

---

## ⏱️ Estimated Times

| Task | Time |
|------|------|
| Production deployment | 10 min |
| Development setup | 5 min |
| SSL setup | 5-10 min |
| First login & explore | 15 min |
| Full security hardening | 1 hour |
| Custom configuration | 30 min |

---

<p align="center">
  <strong>You're ready to go! 🎉</strong>
</p>

<p align="center">
  Choose production or development above and follow the steps.
</p>
