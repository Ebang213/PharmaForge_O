"""
Database preflight check to ensure connectivity before starting the application.
Provides clear instructions if authentication fails due to stale Docker volumes.
"""
import sys
import time
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from app.core.config import settings

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("db_preflight")

def run_db_preflight(retries: int = 5, delay: int = 2):
    """
    Attempts to connect to the database and runs a simple query.
    If connection fails, logs specific troubleshooting steps.
    """
    db_url = settings.DATABASE_URL
    if not db_url:
        logger.error("CRITICAL: DATABASE_URL is not configured!")
        sys.exit(1)

    # Scramble password in logs for security
    safe_url = db_url.split("@")[-1] if "@" in db_url else "configured URL"
    logger.info(f"Running DB preflight check against: {safe_url}")

    engine = create_engine(db_url, connect_args={"connect_timeout": 5})
    
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful.")
            return True
        except OperationalError as e:
            err_msg = str(e)
            
            # Specific check for password authentication failure
            if "password authentication failed" in err_msg.lower():
                logger.error("=" * 60)
                logger.error("FATAL: DATABASE AUTHENTICATION FAILED")
                logger.error("-" * 60)
                logger.error(f"User: {settings.POSTGRES_USER}")
                logger.error(f"Target DB: {settings.POSTGRES_DB}")
                logger.error("-" * 60)
                logger.error("CAUSE: Likely 'Credential Drift'. Your .env / compose settings")
                logger.error("do not match the credentials stored in the existing Docker volume.")
                logger.error("-" * 60)
                logger.error("FIX (Development): Run 'docker compose down -v' to reset data.")
                logger.error("FIX (Production): Run 'scripts/rotate-db-password.ps1' to sync DB.")
                logger.error("=" * 60)
                sys.exit(1)
            
            if attempt < retries:
                logger.warning(f"Attempt {attempt}/{retries} failed: {err_msg}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"CRITICAL: Could not connect to database after {retries} attempts.")
                logger.error(f"Error: {err_msg}")
                sys.exit(1)

if __name__ == "__main__":
    run_db_preflight()
