"""
Evidence processing Celery tasks — text extraction from uploaded documents.
"""
from app.core.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(bind=True, name="evidence.process_text")
def process_evidence_text(self, evidence_id: int):
    """Read an uploaded evidence file from disk and extract its text content.

    Updates the Evidence record with extracted text and transitions the status
    from PENDING → PROCESSING → PROCESSED (or FAILED).
    """
    from datetime import datetime, timezone
    from app.db.session import get_db_context
    from app.db.models import Evidence, EvidenceStatus
    from app.core.metrics import EVIDENCE_PROCESSING_TOTAL
    from app.api.evidence import extract_text_from_file

    with get_db_context() as db:
        evidence = db.query(Evidence).filter(Evidence.id == evidence_id).first()
        if not evidence:
            logger.error(f"Evidence {evidence_id} not found")
            return {"evidence_id": evidence_id, "status": "error", "detail": "not found"}

        evidence.status = EvidenceStatus.PROCESSING
        db.flush()

        try:
            with open(evidence.storage_path, "rb") as f:
                content = f.read()

            extracted_text = extract_text_from_file(
                content, evidence.content_type or "", evidence.filename or ""
            )

            if extracted_text and not extracted_text.startswith("["):
                evidence.extracted_text = extracted_text
                evidence.status = EvidenceStatus.PROCESSED
                evidence.processed_at = datetime.now(timezone.utc)
                status_str = "processed"
            elif extracted_text and extracted_text.startswith("["):
                # Extraction returned an error message (e.g. "[PDF extraction failed: ...]")
                evidence.extracted_text = extracted_text
                evidence.status = EvidenceStatus.FAILED
                evidence.error_message = extracted_text
                evidence.processed_at = datetime.now(timezone.utc)
                status_str = "failed"
            else:
                # Empty but valid extraction
                evidence.status = EvidenceStatus.PROCESSED
                evidence.processed_at = datetime.now(timezone.utc)
                status_str = "processed"

        except Exception as e:
            evidence.status = EvidenceStatus.FAILED
            evidence.error_message = str(e)
            evidence.processed_at = datetime.now(timezone.utc)
            status_str = "failed"
            logger.error(f"Evidence {evidence_id} processing failed: {e}")

        EVIDENCE_PROCESSING_TOTAL.labels(status=status_str).inc()

    logger.info(
        "Evidence text extraction complete",
        extra={
            "service": "evidence",
            "event": "evidence_processed",
            "evidence_id": evidence_id,
            "status": status_str,
        },
    )
    return {"evidence_id": evidence_id, "status": status_str}
