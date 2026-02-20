"""
PharmaForge OS - Main FastAPI Application
Operating System for Virtual Pharma
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.db.session import init_db, engine

# Setup logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting PharmaForge OS...")

    # Initialize database
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    # Create upload directories
    os.makedirs(os.path.join(settings.UPLOAD_DIR, "epcis"), exist_ok=True)
    os.makedirs(os.path.join(settings.UPLOAD_DIR, "documents"), exist_ok=True)

    yield

    logger.info("Shutting down PharmaForge OS...")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Operating System for Virtual Pharma - Supply Chain, Compliance & Regulatory Intelligence",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else "/docs",
    redoc_url="/redoc" if settings.DEBUG else "/redoc",
)

# CORS middleware — restrict methods/headers in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)


# Import and include routers
from app.api.auth import router as auth_router
from app.api.orgs import router as orgs_router
from app.api.vendors import router as vendors_router
from app.api.watchtower import router as watchtower_router
from app.api.dscsa import router as dscsa_router
from app.api.copilot import router as copilot_router
from app.api.war_council import router as war_council_router
from app.api.audit import router as audit_router
from app.api.sourcing import router as sourcing_router
from app.api.admin import router as admin_router
from app.api.evidence import router as evidence_router
from app.api.risk_findings import router as risk_findings_router

app.include_router(auth_router)
app.include_router(orgs_router)
app.include_router(vendors_router)
app.include_router(watchtower_router)
app.include_router(dscsa_router)
app.include_router(copilot_router)
app.include_router(war_council_router)
app.include_router(audit_router)
app.include_router(sourcing_router)
app.include_router(admin_router)
app.include_router(evidence_router)
app.include_router(risk_findings_router)


# Health check endpoint — actually verifies backend connectivity
@app.get("/api/health")
async def health_check():
    """Health check that verifies PostgreSQL and Redis connectivity."""
    checks = {}
    healthy = True

    # Check PostgreSQL
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {type(e).__name__}"
        healthy = False

    # Check Redis
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {type(e).__name__}"
        healthy = False

    status_code = 200 if healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if healthy else "degraded",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "checks": checks,
        },
    )


# Global exception handler — never expose internals to clients
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler — logs full traceback, returns generic 500."""
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)

    # Get the origin from request headers for CORS
    origin = request.headers.get("origin", "")

    # Build CORS headers if origin is allowed
    headers = {}
    if origin and origin in settings.CORS_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=headers,
    )


# Run with uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
