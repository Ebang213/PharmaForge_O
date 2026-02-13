"""
Background worker using RQ (Redis Queue).
"""
import os
import sys

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from redis import Redis
from rq import Worker, Queue, Connection

from app.core.config import settings
from app.core.logging import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


def run_worker():
    """Start the RQ worker."""
    redis_conn = Redis.from_url(settings.REDIS_URL)
    
    with Connection(redis_conn):
        worker = Worker(
            queues=[
                Queue("high", connection=redis_conn),
                Queue("default", connection=redis_conn),
                Queue("low", connection=redis_conn),
            ],
            name="pharmaforge-worker",
        )
        logger.info("Starting PharmaForge worker...")
        worker.work()


if __name__ == "__main__":
    run_worker()
