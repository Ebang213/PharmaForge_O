"""
Watchtower Celery tasks — feed ingestion and risk score recalculation.
"""
import asyncio
import time
from typing import Optional

from app.core.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(bind=True, name="watchtower.sync_feeds")
def sync_feeds(self, source: Optional[str], force: bool, user_id: int, org_id: int):
    """Sync Watchtower feeds from external providers (FDA recalls, shortages, etc.)."""
    from app.db.session import SessionLocal
    from app.db.models import AuditLog
    from app.core.metrics import (
        WATCHTOWER_FEED_SYNC_DURATION,
        WATCHTOWER_FEED_ITEMS_PROCESSED,
    )
    from app.services.watchtower.feed_service import sync_provider, sync_all_providers

    logger.info(
        "Feed sync task started",
        extra={"service": "watchtower", "event": "feed_sync_start", "source": source or "all"},
    )

    sync_start = time.perf_counter()
    db = SessionLocal()
    try:
        if source:
            result = asyncio.run(sync_provider(source, db, force=force))
            response_data = {
                "status": "ok" if result.get("success") else "error",
                "degraded": not result.get("success"),
                "results": [result],
                "total_items_added": result.get("items_added", 0),
                "sources_succeeded": 1 if result.get("success") else 0,
                "sources_failed": 0 if result.get("success") else 1,
            }
        else:
            response_data = asyncio.run(sync_all_providers(db, force=force))
    except Exception as e:
        logger.error(f"Sync error: {e}", exc_info=True)
        try:
            db.rollback()
        except Exception:
            pass
        response_data = {
            "status": "error",
            "degraded": True,
            "results": [{"source": source or "all", "success": False, "error": str(e)}],
            "total_items_added": 0,
            "sources_succeeded": 0,
            "sources_failed": 1,
        }

    # Write audit log in a separate try block
    try:
        if db.is_active:
            try:
                db.rollback()
            except Exception:
                pass

        audit_log = AuditLog(
            user_id=user_id,
            organization_id=org_id,
            action="watchtower_sync",
            entity_type="watchtower",
            details={
                "source": source or "all",
                "force": force,
                "status": response_data.get("status"),
                "degraded": response_data.get("degraded"),
                "total_items_added": response_data.get("total_items_added"),
                "sources_succeeded": response_data.get("sources_succeeded"),
                "sources_failed": response_data.get("sources_failed"),
            },
        )
        db.add(audit_log)
        db.commit()
    except Exception as audit_err:
        logger.error(f"Audit log write failed: {audit_err}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()

    # Prometheus metrics
    sync_elapsed = time.perf_counter() - sync_start
    WATCHTOWER_FEED_SYNC_DURATION.labels(source=source or "all").observe(sync_elapsed)
    items_added = response_data.get("total_items_added", 0)
    if items_added:
        WATCHTOWER_FEED_ITEMS_PROCESSED.labels(source=source or "all").inc(items_added)

    logger.info(
        "Feed sync task completed",
        extra={
            "service": "watchtower",
            "event": "feed_sync",
            "source": source or "all",
            "items_processed": items_added,
            "duration_seconds": round(sync_elapsed, 3),
        },
    )
    return response_data


@celery_app.task(bind=True, name="watchtower.recalculate_risk")
def recalculate_risk(self, org_id: int, user_id: int):
    """Recalculate risk scores for all vendors and facilities in an organisation."""
    from app.db.session import get_db_context
    from app.db.models import Vendor, Facility, AuditLog
    from app.services.risk_scoring import calculate_vendor_risk, calculate_facility_risk

    with get_db_context() as db:
        vendors = db.query(Vendor).filter(Vendor.organization_id == org_id).all()
        for vendor in vendors:
            risk_score, risk_level = calculate_vendor_risk(db, vendor)
            vendor.risk_score = risk_score
            vendor.risk_level = risk_level

        facilities = db.query(Facility).filter(Facility.organization_id == org_id).all()
        for facility in facilities:
            risk_score, risk_level = calculate_facility_risk(db, facility)
            facility.risk_score = risk_score
            facility.risk_level = risk_level

        audit_log = AuditLog(
            user_id=user_id,
            organization_id=org_id,
            action="recalculate_risk",
            entity_type="watchtower",
            details={
                "vendors_updated": len(vendors),
                "facilities_updated": len(facilities),
            },
        )
        db.add(audit_log)

    logger.info(
        "Risk recalculation complete",
        extra={
            "service": "watchtower",
            "event": "risk_recalculation",
            "org_id": org_id,
            "vendors_updated": len(vendors),
            "facilities_updated": len(facilities),
        },
    )
    return {
        "vendors_updated": len(vendors),
        "facilities_updated": len(facilities),
    }
