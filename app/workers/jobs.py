"""
Background job definitions.
"""
from redis import Redis
from rq import Queue
from rq_scheduler import Scheduler
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_queue(name: str = "default") -> Queue:
    """Get RQ queue."""
    redis_conn = Redis.from_url(settings.REDIS_URL)
    return Queue(name, connection=redis_conn)


def get_scheduler() -> Scheduler:
    """Get RQ scheduler."""
    redis_conn = Redis.from_url(settings.REDIS_URL)
    return Scheduler(connection=redis_conn)


# ============= JOB FUNCTIONS =============

def process_document_job(document_id: int):
    """Background job to process document for RAG."""
    from app.services.rag_ingest import process_document_async
    logger.info(f"Processing document {document_id}")
    process_document_async(document_id)


def ingest_watchtower_job():
    """Background job to ingest Watchtower events."""
    from app.services.watchtower_ingest import ingest_fda_events
    logger.info("Running Watchtower ingestion")
    ingest_fda_events()


def recalculate_risk_job(org_id: int = None):
    """Background job to recalculate risk scores."""
    from app.db.session import get_db_context
    from app.db.models import Vendor, Facility
    from app.services.risk_scoring import calculate_vendor_risk, calculate_facility_risk
    
    logger.info(f"Recalculating risk scores for org {org_id or 'all'}")
    
    with get_db_context() as db:
        query = db.query(Vendor)
        if org_id:
            query = query.filter(Vendor.organization_id == org_id)
        
        for vendor in query.all():
            risk_score, risk_level = calculate_vendor_risk(db, vendor)
            vendor.risk_score = risk_score
            vendor.risk_level = risk_level
        
        fac_query = db.query(Facility)
        if org_id:
            fac_query = fac_query.filter(Facility.organization_id == org_id)
        
        for facility in fac_query.all():
            risk_score, risk_level = calculate_facility_risk(db, facility)
            facility.risk_score = risk_score
            facility.risk_level = risk_level


def send_rfq_email_job(message_id: int):
    """Background job to send approved RFQ email."""
    from app.db.session import get_db_context
    from app.db.models import RFQMessage, MessageStatus
    
    logger.info(f"Sending RFQ message {message_id}")
    
    with get_db_context() as db:
        message = db.query(RFQMessage).filter(RFQMessage.id == message_id).first()
        if not message or message.status != MessageStatus.APPROVED:
            logger.warning(f"Message {message_id} not found or not approved")
            return
        
        try:
            # In production, integrate with email service (SendGrid, SES, etc.)
            # For now, just mark as sent
            message.status = MessageStatus.SENT
            message.sent_at = datetime.utcnow()
            logger.info(f"Message {message_id} marked as sent (email integration pending)")
        except Exception as e:
            message.status = MessageStatus.FAILED
            message.send_error = str(e)
            logger.error(f"Failed to send message {message_id}: {e}")


# ============= QUEUE HELPERS =============

def enqueue_document_processing(document_id: int):
    """Queue document for processing."""
    queue = get_queue("default")
    return queue.enqueue(process_document_job, document_id)


def enqueue_watchtower_ingestion():
    """Queue Watchtower ingestion."""
    queue = get_queue("low")
    return queue.enqueue(ingest_watchtower_job)


def enqueue_risk_recalculation(org_id: int = None):
    """Queue risk recalculation."""
    queue = get_queue("default")
    return queue.enqueue(recalculate_risk_job, org_id)


def enqueue_rfq_email(message_id: int):
    """Queue RFQ email sending."""
    queue = get_queue("high")
    return queue.enqueue(send_rfq_email_job, message_id)


def setup_scheduled_jobs():
    """Setup scheduled jobs."""
    scheduler = get_scheduler()
    
    # Daily Watchtower ingestion at 6 AM UTC
    scheduler.schedule(
        scheduled_time=datetime.utcnow(),
        func=ingest_watchtower_job,
        interval=86400,  # 24 hours
        repeat=None,
    )
    
    # Daily risk recalculation at 7 AM UTC
    scheduler.schedule(
        scheduled_time=datetime.utcnow() + timedelta(hours=1),
        func=recalculate_risk_job,
        interval=86400,
        repeat=None,
    )
    
    logger.info("Scheduled jobs configured")
