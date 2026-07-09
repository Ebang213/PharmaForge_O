# PharmaForge — DSCSA compliance for independent pharmacies.

PharmaForge helps small dispensers meet DSCSA requirements: it receives,
validates, and stores your EPCIS data, tracks trading partner licenses, and
produces audit packets you can hand to an inspector.

**Status: pilot.** PharmaForge is in active pilot with early pharmacy users.
It is not yet a finished production product, and it does not guarantee
compliance — it helps you meet DSCSA requirements.

---

## Why now

The FDA exemption for small dispensers — pharmacies with **25 or fewer
full-time pharmacists and pharmacy technicians** — ends on
**November 27, 2026**. After that date, dispensers must be interoperable
with the electronic drug tracing system: able to receive, validate, and
store serialized EPCIS transaction data from their trading partners.
(For larger dispensers, the deadline was November 27, 2025.)

PharmaForge gives an independent pharmacy that capability without an
enterprise IT project: **$149/month, no setup fee, cancel anytime, free
60-day pilot.**

## What it does

- **Receive & validate EPCIS files** — upload JSON/XML EPCIS files from your
  wholesalers; PharmaForge parses them, checks them against DSCSA
  requirements, and flags issues like chain-of-custody breaks.
- **Track trading partner licenses** — keep GLN, DEA number, and state
  license data for every wholesaler and distributor you buy from.
- **One-click audit packets** — export a bundle of your transaction data,
  validation results, and audit trail for an inspection.
- **Compliance readiness score** — a dashboard score showing exactly what is
  left to do before the deadline.

---

## Quick start (development)

Prerequisites: Docker 20.10+ and Docker Compose 2.0+.

```bash
git clone <repository-url>
cd PharmaForge_O
cp .env.example .env
docker compose up --build
```

Then:

- **Frontend**: http://localhost:5173 (landing page; register your pharmacy)
- **API**: http://localhost:8001
- **API docs**: http://localhost:8001/docs

Public self-registration is controlled by `ALLOW_PUBLIC_REGISTRATION`; an
initial admin can also be created with the `ADMIN_BOOTSTRAP_EMAIL` /
`ADMIN_BOOTSTRAP_PASSWORD` env vars.

### Production

See [PRODUCTION.md](./PRODUCTION.md). In short: `cp .env.production .env`,
set `SECRET_KEY`, `POSTGRES_PASSWORD`, and `REDIS_PASSWORD`, then run
`./deploy.sh deploy` (or `.\deploy.ps1 deploy` on Windows).

---

## Architecture

| Layer | Technology |
|-------|------------|
| Frontend | React 18 + TypeScript + Vite |
| API | FastAPI (Python 3.11) |
| Database | PostgreSQL 15, migrations via Alembic |
| Cache / queue | Redis 7 (RQ + Celery workers) |
| Vector DB | Qdrant (used by optional enterprise modules) |
| Web server | NGINX (production) |

```
Browser → NGINX → FastAPI (/api/*) → PostgreSQL
                → React SPA (static)   Redis · Qdrant
```

The core compliance engine lives in `app/services/epcis_parse.py` and
`app/services/epcis_validate.py`, with the upload API in `app/api/dscsa.py`
and the readiness score in `app/api/compliance.py`.

Enterprise modules (Mission Control, Watchtower, Copilot, War Council,
Sourcing) are hidden behind the `VITE_ENTERPRISE_FEATURES` flag (default
`false`). See [docs/vision.md](./docs/vision.md) for the long-term vision.

---

## Testing

```bash
# Backend (requires the Postgres/Redis services)
docker compose exec api pytest

# Frontend build
cd frontend && npm run build
```

CI runs migrations, the backend suite, and dependency security scans on
every pull request (`.github/workflows/ci.yml`).

### Migrations

```bash
docker compose exec api alembic upgrade head
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [PRODUCTION.md](./PRODUCTION.md) | Production deployment guide |
| [docs/vision.md](./docs/vision.md) | Long-term enterprise vision |
| [docs/migrations.md](./docs/migrations.md) | Migration notes |

## License

MIT License — see [LICENSE](./LICENSE).

---

*PharmaForge helps you meet DSCSA requirements. It does not provide legal
advice and is not endorsed by the FDA.*
