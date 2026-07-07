"""
Compliance readiness API for the pharmacy DSCSA MVP.

Computes a 0-100 readiness score from existing data — no new tables.
Four checks, 25 points each:
1. At least one trading partner with complete license/identifier data
2. At least one EPCIS upload in the last 30 days
3. Most recent EPCIS upload passed validation
4. At least one audit packet generated

Endpoint: GET /api/compliance/readiness
"""
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.db.models import Vendor, EPCISUpload, AuditLog, EPCISValidationStatus
from app.core.rbac import get_current_user_context
from app.api.trading_partners import compute_readiness

router = APIRouter(prefix="/api/compliance", tags=["Compliance"])

RECENT_UPLOAD_WINDOW_DAYS = 30
POINTS_PER_CHECK = 25


# ============= SCHEMAS =============

class ReadinessCheck(BaseModel):
    id: str
    label: str
    passed: bool
    detail: str


class ReadinessResponse(BaseModel):
    score: int
    checks: List[ReadinessCheck]


# ============= HELPERS =============

def _status_value(status, default: str = "pending") -> str:
    """Normalize an enum-or-string validation status to its string value."""
    if status is None:
        return default
    if hasattr(status, "value"):
        return status.value
    return str(status)


def _check_trading_partner(db: Session, org_id: int) -> ReadinessCheck:
    partners = db.query(Vendor).filter(Vendor.organization_id == org_id).all()
    verified = [p for p in partners if compute_readiness(p)[0] == "verified"]
    if verified:
        detail = f"{len(verified)} trading partner(s) with complete license data."
    elif partners:
        detail = (
            f"{len(partners)} trading partner(s) exist but none has complete "
            "license data. Add a GLN, DEA number, or state license number "
            "plus contact info."
        )
    else:
        detail = "Add your first trading partner (wholesaler or distributor)."
    return ReadinessCheck(
        id="trading_partner_license",
        label="Trading partner with license data",
        passed=bool(verified),
        detail=detail,
    )


def _check_recent_upload(db: Session, org_id: int) -> ReadinessCheck:
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_UPLOAD_WINDOW_DAYS)
    recent_count = db.query(EPCISUpload).filter(
        EPCISUpload.organization_id == org_id,
        EPCISUpload.created_at >= cutoff,
    ).count()
    if recent_count:
        detail = f"{recent_count} EPCIS upload(s) in the last {RECENT_UPLOAD_WINDOW_DAYS} days."
    else:
        detail = f"No EPCIS uploads in the last {RECENT_UPLOAD_WINDOW_DAYS} days. Upload a file from your wholesaler."
    return ReadinessCheck(
        id="recent_epcis_upload",
        label=f"EPCIS upload in the last {RECENT_UPLOAD_WINDOW_DAYS} days",
        passed=recent_count > 0,
        detail=detail,
    )


def _check_latest_upload_valid(db: Session, org_id: int) -> ReadinessCheck:
    latest: Optional[EPCISUpload] = db.query(EPCISUpload).filter(
        EPCISUpload.organization_id == org_id,
    ).order_by(desc(EPCISUpload.created_at), desc(EPCISUpload.id)).first()

    if latest is None:
        passed = False
        detail = "No EPCIS uploads yet."
    else:
        status = _status_value(latest.validation_status)
        passed = status == EPCISValidationStatus.VALID.value
        if passed:
            detail = f"Most recent upload '{latest.filename}' passed validation."
        else:
            detail = f"Most recent upload '{latest.filename}' has status '{status}'. Review and re-upload."
    return ReadinessCheck(
        id="latest_upload_valid",
        label="Most recent upload passed validation",
        passed=passed,
        detail=detail,
    )


def _check_audit_packet(db: Session, org_id: int) -> ReadinessCheck:
    packet_count = db.query(AuditLog).filter(
        AuditLog.organization_id == org_id,
        AuditLog.action == "audit_packet_generated",
    ).count()
    if packet_count:
        detail = f"{packet_count} audit packet(s) generated."
    else:
        detail = "No audit packet generated yet. Generate one so you can hand it to an inspector."
    return ReadinessCheck(
        id="audit_packet_generated",
        label="Audit packet generated",
        passed=packet_count > 0,
        detail=detail,
    )


# ============= ROUTES =============

@router.get("/readiness", response_model=ReadinessResponse)
async def get_compliance_readiness(
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    """Compliance readiness score (0-100) with per-check breakdown."""
    org_id = user_context["org_id"]
    checks = [
        _check_trading_partner(db, org_id),
        _check_recent_upload(db, org_id),
        _check_latest_upload_valid(db, org_id),
        _check_audit_packet(db, org_id),
    ]
    score = sum(POINTS_PER_CHECK for c in checks if c.passed)
    return ReadinessResponse(score=score, checks=checks)
