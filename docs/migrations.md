# Database Migration Commands

## First Deployment (Fresh DB)

After `docker-compose up -d`, run migrations:

```powershell
docker exec pharmaforge_api sh -c "cd /code && alembic upgrade head"
```

Then restart the API to trigger bootstrap:

```powershell
docker-compose -f docker-compose.prod.yml restart api worker
```

## Subsequent Deployments

If you add new migrations, run:

```powershell
docker exec pharmaforge_api sh -c "cd /code && alembic upgrade head"
docker-compose -f docker-compose.prod.yml restart api worker
```

## Creating New Migrations

From your local machine (with postgres accessible):

```bash
# Set DATABASE_URL for local postgres
export DATABASE_URL=postgresql://user:pass@localhost:5432/pharmaforge

# Auto-generate migration
alembic revision --autogenerate -m "description of changes"

# Edit the generated file if needed, then apply
alembic upgrade head
```

## Rollback

```powershell
# Roll back one step
docker exec pharmaforge_api sh -c "cd /code && alembic downgrade -1"

# Roll back to specific revision
docker exec pharmaforge_api sh -c "cd /code && alembic downgrade 001_initial"
```

## View Current Version

```powershell
docker exec pharmaforge_api sh -c "cd /code && alembic current"
```
