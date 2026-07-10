"""
Compliance readiness API for the pharmacy DSCSA MVP.

Single authoritative source for dashboard readiness — the frontend must not
recompute any of this. Five checks, 20 points each:
1. At least one verified trading partner
2. At least one EPCIS upload in the recent window
3. Most recent EPCIS upload passed validation
4. No unresolved chain breaks or critical issues on the latest upload
5. Inspection packet generated for the latest valid upload

The response also carries active_alert_count / blocking_issue_count derived
from the same queries, so the dashboard alert badge can never contradict the
database state.

Limitation: the data model has no way to mark a chain break or issue as
resolved (EPCISIssue has no resolution column), so check 4 is scoped to the
issues present on the LATEST upload only — re-uploading a corrected file is
the only resolution path.

Endpoint: GET /api/compliance/readiness
"""
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.db.models import (
    Vendor, EPCISUpload, EPCISIssue, AuditLog, EPCISValidationStatus, RiskLevel,
)
from app.core.rbac import get_current_user_context
from app.api.trading_partners import compute_readiness

router = APIRouter(prefix="/api/compliance", tags=["Compliance"])

RECENT_UPLOAD_WINDOW_DAYS = 30
POINTS_PER_CHECK = 20


# ============= SCHEMAS =============

class ReadinessCheck(BaseModel):
    id: str
    label: str
    passed: bool
    detail: str


class ReadinessResponse(BaseModel):
    score: int
    checks: List[ReadinessCheck]
    active_alert_count: int
    blocking_issue_count: int
    latest_upload_id: Optional[int]
    latest_upload_status: Optional[str]


# ============= HELPERS =============

def _status_value(status, default: str = "pending") -> str:
    """Normalize an enum-or-string validation status to its string value."""
    if status is None:
        return default
    if hasattr(status, "value"):
        return status.value
    return str(status)


class _OrgReadinessState:
    """All org-scoped facts the checks and alert counts are derived from."""

    def __init__(self, db: Session, org_id: int):
        self.partners = db.query(Vendor).filter(
            Vendor.organization_id == org_id,
        ).all()
        self.verified_partners = [
            p for p in self.partners if compute_readiness(p)[0] == "verified"
        ]
        self.incomplete_active_partners = [
            p for p in self.partners
            if (p.partner_status or "active") == "active"
            and compute_readiness(p)[0] != "verified"
        ]

        cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_UPLOAD_WINDOW_DAYS)
        self.recent_upload_count = db.query(EPCISUpload).filter(
            EPCISUpload.organization_id == org_id,
            EPCISUpload.created_at >= cutoff,
        ).count()

        self.latest_upload: Optional[EPCISUpload] = db.query(EPCISUpload).filter(
            EPCISUpload.organization_id == org_id,
        ).order_by(desc(EPCISUpload.created_at), desc(EPCISUpload.id)).first()

        self.latest_valid_upload: Optional[EPCISUpload] = db.query(EPCISUpload).filter(
            EPCISUpload.organization_id == org_id,
            EPCISUpload.validation_status == EPCISValidationStatus.VALID,
        ).order_by(desc(EPCISUpload.created_at), desc(EPCISUpload.id)).first()

        # Chain breaks / critical issues on the latest upload only (see module
        # docstring: no resolution mechanism exists, older uploads are
        # superseded by re-uploading a corrected file).
        self.latest_chain_break_count = 0
        self.latest_critical_issue_count = 0
        if self.latest_upload is not None:
            self.latest_chain_break_count = self.latest_upload.chain_break_count or 0
            self.latest_critical_issue_count = db.query(EPCISIssue).filter(
                EPCISIssue.upload_id == self.latest_upload.id,
                EPCISIssue.severity == RiskLevel.CRITICAL,
            ).count()

        # Packet-generation events for the latest valid upload. Only a real
        # audit_packet_generated event counts — a valid upload alone is not
        # an inspection packet.
        self.packet_event_count = 0
        if self.latest_valid_upload is not None:
            self.packet_event_count = db.query(AuditLog).filter(
                AuditLog.organization_id == org_id,
                AuditLog.action == "audit_packet_generated",
                AuditLog.entity_type == "epcis_upload",
                AuditLog.entity_id == self.latest_valid_upload.id,
            ).count()


def _check_trading_partner(state: _OrgReadinessState) -> ReadinessCheck:
    verified = state.verified_partners
    if verified:
        detail = f"{len(verified)} trading partner(s) with complete license data."
    elif state.partners:
        detail = (
            f"{len(state.partners)} trading partner(s) exist but none has complete "
            "license data. Add a GLN, DEA number, or state license number "
            "plus contact info."
        )
    else:
        detail = "Add your first trading partner (wholesaler or distributor)."
    return ReadinessCheck(
        id="trading_partner_license",
        label="At least one verified trading partner",
        passed=bool(verified),
        detail=detail,
    )


def _check_recent_upload(state: _OrgReadinessState) -> ReadinessCheck:
    if state.recent_upload_count:
        detail = f"{state.recent_upload_count} EPCIS upload(s) in the last {RECENT_UPLOAD_WINDOW_DAYS} days."
    else:
        detail = f"No EPCIS uploads in the last {RECENT_UPLOAD_WINDOW_DAYS} days. Upload a file from your wholesaler."
    return ReadinessCheck(
        id="recent_epcis_upload",
        label=f"EPCIS upload in the last {RECENT_UPLOAD_WINDOW_DAYS} days",
        passed=state.recent_upload_count > 0,
        detail=detail,
    )


def _check_latest_upload_valid(state: _OrgReadinessState) -> ReadinessCheck:
    latest = state.latest_upload
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
        label="Latest EPCIS upload is valid",
        passed=passed,
        detail=detail,
    )


def _check_chain_integrity(state: _OrgReadinessState) -> ReadinessCheck:
    latest = state.latest_upload
    if latest is None:
        passed = False
        detail = "No EPCIS uploads yet."
    else:
        problems = []
        if state.latest_chain_break_count:
            problems.append(f"{state.latest_chain_break_count} chain break(s)")
        if state.latest_critical_issue_count:
            problems.append(f"{state.latest_critical_issue_count} critical issue(s)")
        passed = not problems
        if passed:
            detail = f"No chain breaks or critical issues on '{latest.filename}'."
        else:
            detail = (
                f"Upload '{latest.filename}' has {' and '.join(problems)}. "
                "Request a corrected file from your trading partner and re-upload."
            )
    return ReadinessCheck(
        id="chain_integrity",
        label="No unresolved chain breaks or critical issues",
        passed=passed,
        detail=detail,
    )


def _check_audit_packet(state: _OrgReadinessState) -> ReadinessCheck:
    latest_valid = state.latest_valid_upload
    if latest_valid is None:
        passed = False
        detail = "No valid EPCIS upload to generate an inspection packet for."
    elif state.packet_event_count == 0:
        passed = False
        detail = (
            f"No inspection packet generated for '{latest_valid.filename}' yet. "
            "Generate one so you can hand it to an inspector."
        )
    else:
        passed = True
        detail = (
            f"Inspection packet generated for '{latest_valid.filename}' "
            f"({state.packet_event_count} generation event(s))."
        )
    return ReadinessCheck(
        id="audit_packet_generated",
        label="Inspection packet generated for the latest valid upload",
        passed=passed,
        detail=detail,
    )


def _count_alerts(state: _OrgReadinessState) -> int:
    """Actionable DSCSA conditions. Enterprise Watchtower alerts are excluded."""
    count = 0
    if state.latest_upload is not None:
        status = _status_value(state.latest_upload.validation_status)
        if status == EPCISValidationStatus.INVALID.value:
            count += 1
        count += state.latest_chain_break_count
        count += state.latest_critical_issue_count
    count += len(state.incomplete_active_partners)
    return count


# ============= ROUTES =============

@router.get("/readiness", response_model=ReadinessResponse)
async def get_compliance_readiness(
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db),
):
    """Compliance readiness score (0-100) with per-check breakdown and alert counts."""
    org_id = user_context["org_id"]
    state = _OrgReadinessState(db, org_id)
    checks = [
        _check_trading_partner(state),
        _check_recent_upload(state),
        _check_latest_upload_valid(state),
        _check_chain_integrity(state),
        _check_audit_packet(state),
    ]
    score = sum(POINTS_PER_CHECK for c in checks if c.passed)
    latest = state.latest_upload
    return ReadinessResponse(
        score=score,
        checks=checks,
        active_alert_count=_count_alerts(state),
        # Data problems that block the chain-integrity check outright
        blocking_issue_count=state.latest_chain_break_count + state.latest_critical_issue_count,
        latest_upload_id=latest.id if latest else None,
        latest_upload_status=_status_value(latest.validation_status) if latest else None,
    )
