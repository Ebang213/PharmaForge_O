"""
Watchtower API routes - Supply chain risk monitoring.
"""
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from app.db.models import (
    WatchtowerEvent, WatchtowerAlert, Vendor, Facility, 
    AuditLog, RiskLevel, Evidence, WatchtowerAlertStatus
)
from app.db.session import get_db
from app.core.rbac import get_current_user_context, Role, has_permission
from app.core.logging import get_logger
from app.services.risk_scoring import calculate_vendor_risk, calculate_facility_risk
from app.services.pdf_extract import extract_text_from_pdf, analyze_document_content
from fastapi import UploadFile, File, Form
import hashlib
import os
from app.core.config import settings

router = APIRouter(prefix="/api/watchtower", tags=["Watchtower"])
logger = get_logger(__name__)


def get_risk_level_str(risk_level) -> str:
    """
    Safely extract risk_level as a string.
    
    Handles both enum instances (RiskLevel.LOW) and string values ("low").
    """
    if risk_level is None:
        return "low"
    if hasattr(risk_level, 'value'):
        return risk_level.value
    return str(risk_level)

def _require_role(user_context: dict, required_role: Role) -> None:
    role = user_context.get("role", Role.VIEWER)
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            role = Role.VIEWER
    if not has_permission(role, required_role):
        raise HTTPException(
            status_code=403,
            detail=f"Insufficient permissions. Required: {required_role.value}",
        )


def _validate_evidence_file(file: UploadFile) -> str:
    filename = file.filename or ""
    if not filename:
        raise HTTPException(status_code=400, detail="File name is required")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".pdf", ".txt"}:
        raise HTTPException(
            status_code=400,
            detail="File type not allowed. Allowed: .pdf, .txt",
        )
    return ext


def _extract_text_from_upload(content: bytes, filename: str, content_type: Optional[str]) -> str:
    if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return extract_text_from_pdf(content)
    if content_type in ("text/plain",) or filename.lower().endswith(".txt"):
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return content.decode("latin-1")
            except Exception:
                return ""
    try:
        return content.decode("utf-8")
    except Exception:
        return ""


def _evidence_status(evidence: Evidence) -> str:
    meta = evidence.meta_data or {}
    if meta.get("extraction_error"):
        return "failed"
    return "processed" if evidence.extracted_text else "pending"


# ============= SCHEMAS =============

class EventResponse(BaseModel):
    id: int
    event_type: str
    source: str
    external_id: Optional[str]
    title: Optional[str]
    description: Optional[str]
    severity: str
    affected_products: Optional[List[str]]
    affected_companies: Optional[List[str]]
    event_date: Optional[datetime]
    source_url: Optional[str]
    created_at: datetime
    
    class Config:
        orm_mode = True


class AlertResponse(BaseModel):
    id: int
    event_id: int
    vendor_id: Optional[int]
    vendor_name: Optional[str]
    facility_id: Optional[int]
    facility_name: Optional[str]
    severity: str
    is_acknowledged: bool
    acknowledged_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    event: Optional[EventResponse]
    
    class Config:
        orm_mode = True


class AlertAcknowledge(BaseModel):
    notes: Optional[str] = None


class ProviderStatus(BaseModel):
    source_id: str
    source_name: str
    category: str
    last_success_at: Optional[datetime]
    last_error_at: Optional[datetime]
    last_error_message: Optional[str]
    last_run_at: Optional[datetime]


class RiskSummary(BaseModel):
    total_vendors: int
    high_risk_vendors: int
    total_facilities: int
    high_risk_facilities: int
    active_alerts: int
    recent_events: int
    evidence_count: int
    feed_items: int
    provider_statuses: List[ProviderStatus]

class VendorCreate(BaseModel):
    name: str
    vendor_code: Optional[str] = None
    vendor_type: Optional[str] = None
    country: Optional[str] = None
    contact_email: Optional[str] = None

class WatchtowerEvidenceUploadResponse(BaseModel):
    id: int
    filename: str
    status: str
    created_at: datetime
    
    class Config:
        orm_mode = True


class WatchtowerEvidenceItem(BaseModel):
    id: int
    filename: str
    content_type: Optional[str]
    uploaded_at: datetime
    status: str
    vendor_id: Optional[int]
    vendor_name: Optional[str]
    source_type: Optional[str]
    source: Optional[str]  # 'watchtower' or 'copilot'
    notes: Optional[str]
    extracted_text_preview: Optional[str]

    class Config:
        orm_mode = True

class AnalysisResponse(BaseModel):
    doc_type: str
    severity: str
    matched_vendor: Optional[str]
    alert_id: Optional[int]
    event_id: Optional[int]


# ============= ROUTES =============

@router.get("/health")
async def watchtower_health(
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """
    Watchtower health/diagnostics endpoint.
    Returns overall system status, per-source status, and data counts.
    
    Response:
    - overall_status: healthy (all sources ok), degraded (some failing), down (all failing)
    - sources: per-source status with timestamps and errors
    - counts: feed_items, active_alerts, vendors, facilities
    """
    import redis
    from app.core.config import settings
    from app.services.watchtower.feed_service import get_health_status
    
    # Get health status from feed service
    health = get_health_status(db)
    
    # Check Redis connection
    redis_connected = False
    try:
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        redis_connected = True
    except Exception:
        pass
    
    # Add additional context
    health["redis_connected"] = redis_connected
    health["demo_mode"] = settings.SEED_DEMO
    
    return health


@router.post("/refresh")
async def watchtower_refresh(
    request: Request,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """
    Trigger an immediate Watchtower data refresh.
    In demo mode, this ensures demo data is seeded. 
    In live mode, this would trigger provider data fetch.
    Operator or higher.
    """
    from app.db.session import seed_demo_data

    _require_role(user_context, Role.OPERATOR)
    
    # Check current data state
    vendor_count_before = db.query(Vendor).filter(
        Vendor.organization_id == user_context["org_id"]
    ).count()
    
    # In demo mode, ensure data is seeded
    if vendor_count_before == 0:
        seed_demo_data()
    
    # Get updated counts
    vendor_count = db.query(Vendor).filter(
        Vendor.organization_id == user_context["org_id"]
    ).count()
    event_count = db.query(WatchtowerEvent).count()
    alert_count = db.query(WatchtowerAlert).filter(
        WatchtowerAlert.organization_id == user_context["org_id"],
        WatchtowerAlert.is_acknowledged == False
    ).count()
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="watchtower_refresh",
        entity_type="watchtower",
        details={"vendors": vendor_count, "events": event_count, "alerts": alert_count},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    
    return {
        "status": "refreshed",
        "demo_mode": True,
        "data_counts": {
            "vendors": vendor_count,
            "events": event_count,
            "alerts": alert_count,
        },
        "message": "Data refresh complete"
    }

@router.get("/summary", response_model=RiskSummary)
async def get_risk_summary(
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Get risk summary dashboard data."""
    org_id = user_context["org_id"]
    
    vendors = db.query(Vendor).filter(Vendor.organization_id == org_id).all()
    facilities = db.query(Facility).filter(Facility.organization_id == org_id).all()
    
    active_alerts = db.query(WatchtowerAlert).filter(
        WatchtowerAlert.organization_id == org_id,
        WatchtowerAlert.status == WatchtowerAlertStatus.ACTIVE
    ).count()
    
    recent_events = db.query(WatchtowerEvent).count()
    evidence_count = db.query(Evidence).filter(
        Evidence.organization_id == org_id,
        or_(Evidence.source == "watchtower", Evidence.alerts.any())
    ).count()

    from app.db.models import WatchtowerItem
    from app.services.watchtower.feed_service import list_providers, get_sync_status

    feed_items = db.query(WatchtowerItem).count()
    provider_statuses: List[ProviderStatus] = []
    for provider in list_providers():
        status = get_sync_status(db, provider["source_id"])
        provider_statuses.append(ProviderStatus(
            source_id=provider["source_id"],
            source_name=provider["source_name"],
            category=provider["category"],
            last_success_at=status.last_success_at if status else None,
            last_error_at=status.last_error_at if status else None,
            last_error_message=status.last_error_message if status else None,
            last_run_at=status.last_run_at if status else None,
        ))
    
    return RiskSummary(
        total_vendors=len(vendors),
        high_risk_vendors=len([v for v in vendors if v.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]]),
        total_facilities=len(facilities),
        high_risk_facilities=len([f for f in facilities if f.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]]),
        active_alerts=active_alerts,
        recent_events=recent_events,
        evidence_count=evidence_count,
        feed_items=feed_items,
        provider_statuses=provider_statuses
    )

# ============= EVIDENCE ENDPOINTS =============

async def _create_watchtower_evidence(
    file: UploadFile,
    user_context: dict,
    db: Session,
    vendor_id: Optional[int] = None,
    vendor_name: Optional[str] = None,
    source_type: Optional[str] = None,
    notes: Optional[str] = None,
) -> Evidence:
    _require_role(user_context, Role.OPERATOR)
    _validate_evidence_file(file)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    sha256 = hashlib.sha256(content).hexdigest()
    existing = db.query(Evidence).filter(
        Evidence.organization_id == user_context["org_id"],
        Evidence.sha256 == sha256,
        Evidence.source == "watchtower"
    ).first()
    if existing:
        return existing

    resolved_vendor_id = vendor_id
    resolved_vendor_name = vendor_name
    if not resolved_vendor_id and vendor_name:
        vendor = db.query(Vendor).filter(
            Vendor.organization_id == user_context["org_id"],
            Vendor.name.ilike(vendor_name.strip())
        ).first()
        if vendor:
            resolved_vendor_id = vendor.id
            resolved_vendor_name = vendor.name

    storage_dir = os.path.join(settings.UPLOAD_DIR, "evidence")
    os.makedirs(storage_dir, exist_ok=True)
    storage_path = os.path.join(storage_dir, f"{sha256}_{file.filename}")

    try:
        with open(storage_path, "wb") as f:
            f.write(content)
    except Exception as exc:
        logger.error(f"Watchtower evidence write failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to store evidence file")

    meta_data = {
        "source_type": source_type,
        "vendor_name": resolved_vendor_name or vendor_name,
        "notes": notes,
    }

    extracted_text = ""
    try:
        extracted_text = _extract_text_from_upload(content, file.filename or "", file.content_type)
    except Exception as exc:
        logger.error(f"Watchtower evidence extraction failed: {exc}")
        meta_data["extraction_error"] = str(exc)

    evidence = Evidence(
        organization_id=user_context["org_id"],
        vendor_id=resolved_vendor_id,
        filename=file.filename or "unnamed",
        content_type=file.content_type,
        storage_path=storage_path,
        sha256=sha256,
        uploaded_by=int(user_context["sub"]),
        extracted_text=extracted_text,
        source="watchtower",
        meta_data=meta_data,
    )
    try:
        db.add(evidence)
        db.commit()
        db.refresh(evidence)
    except Exception as exc:
        db.rollback()
        logger.error(f"Watchtower evidence DB write failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to save evidence record")

    return evidence


@router.post("/evidence", response_model=WatchtowerEvidenceUploadResponse)
async def upload_watchtower_evidence(
    request: Request,
    file: UploadFile = File(...),
    source_type: Optional[str] = Form(None),
    vendor_name: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    vendor_id: Optional[int] = Form(None),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Upload a new evidence document (PDF/TXT)."""
    evidence = await _create_watchtower_evidence(
        file=file,
        user_context=user_context,
        db=db,
        vendor_id=vendor_id,
        vendor_name=vendor_name,
        source_type=source_type,
        notes=notes,
    )

    return WatchtowerEvidenceUploadResponse(
        id=evidence.id,
        filename=evidence.filename,
        status=_evidence_status(evidence),
        created_at=evidence.uploaded_at,
    )


@router.post("/evidence/upload", response_model=WatchtowerEvidenceUploadResponse)
async def upload_evidence_legacy(
    request: Request,
    file: UploadFile = File(...),
    vendor_id: Optional[int] = Form(None),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Legacy Watchtower evidence upload endpoint."""
    evidence = await _create_watchtower_evidence(
        file=file,
        user_context=user_context,
        db=db,
        vendor_id=vendor_id,
    )

    return WatchtowerEvidenceUploadResponse(
        id=evidence.id,
        filename=evidence.filename,
        status=_evidence_status(evidence),
        created_at=evidence.uploaded_at,
    )


@router.get("/evidence", response_model=List[WatchtowerEvidenceItem])
async def list_watchtower_evidence(
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """List Watchtower evidence uploads for the current organization."""
    evidence_list = db.query(Evidence).filter(
        Evidence.organization_id == user_context["org_id"],
        or_(Evidence.source == "watchtower", Evidence.alerts.any())
    ).order_by(desc(Evidence.uploaded_at)).offset(offset).limit(limit).all()

    results: List[WatchtowerEvidenceItem] = []
    for evidence in evidence_list:
        meta = evidence.meta_data or {}
        preview = None
        if evidence.extracted_text:
            preview = evidence.extracted_text[:240]
        results.append(WatchtowerEvidenceItem(
            id=evidence.id,
            filename=evidence.filename,
            content_type=evidence.content_type,
            uploaded_at=evidence.uploaded_at,
            status=_evidence_status(evidence),
            vendor_id=evidence.vendor_id,
            vendor_name=evidence.vendor.name if evidence.vendor else meta.get("vendor_name"),
            source_type=meta.get("source_type"),
            source=evidence.source or "upload",
            notes=meta.get("notes"),
            extracted_text_preview=preview,
        ))

    return results

@router.post("/evidence/{evidence_id}/analyze", response_model=AnalysisResponse)
async def analyze_evidence(
    evidence_id: int,
    request: Request,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Extract text from evidence and generate alerts."""
    _require_role(user_context, Role.OPERATOR)
    evidence = db.query(Evidence).filter(
        Evidence.id == evidence_id,
        Evidence.organization_id == user_context["org_id"]
    ).first()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
        
    # 1. Extract text
    extracted_text = evidence.extracted_text or ""
    if not extracted_text:
        try:
            with open(evidence.storage_path, "rb") as f:
                content = f.read()
        except Exception as exc:
            logger.error(f"Failed to read evidence file: {exc}")
            raise HTTPException(status_code=500, detail="Failed to read evidence file")

        if evidence.content_type == "application/pdf" or evidence.filename.lower().endswith(".pdf"):
            extracted_text = extract_text_from_pdf(content)
        else:
            try:
                extracted_text = content.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    extracted_text = content.decode("latin-1")
                except Exception:
                    extracted_text = ""

        evidence.extracted_text = extracted_text
        if evidence.source != "watchtower":
            evidence.source = "watchtower"
    
    # 2. Analyze
    vendors = db.query(Vendor).filter(Vendor.organization_id == user_context["org_id"]).all()
    analysis = analyze_document_content(extracted_text, vendors)
    
    # Use provided vendor_id if any, else use matched
    final_vendor_id = evidence.vendor_id or analysis["matched_vendor_id"]
    
    # 3. Create Alert/Event
    event = WatchtowerEvent(
        vendor_id=final_vendor_id,
        event_type=analysis["doc_type"],
        source="upload",
        title=analysis["title"],
        description=analysis["description"][:500], # Trucate for display
        severity=analysis["severity"],
        event_date=evidence.uploaded_at,
        raw_data={"evidence_id": evidence.id}
    )
    db.add(event)
    db.flush()
    
    alert = WatchtowerAlert(
        organization_id=user_context["org_id"],
        event_id=event.id,
        vendor_id=final_vendor_id,
        evidence_id=evidence.id,
        severity=analysis["severity"],
        title=analysis["title"],
        description=analysis["description"],
        status=WatchtowerAlertStatus.ACTIVE,
        source="upload"
    )
    db.add(alert)
    db.commit()
    db.refresh(event)
    db.refresh(alert)
    
    matched_vendor_name = None
    if final_vendor_id:
        v = db.query(Vendor).get(final_vendor_id)
        matched_vendor_name = v.name if v else None
        
    return AnalysisResponse(
        doc_type=analysis["doc_type"],
        severity=analysis["severity"].value,
        matched_vendor=matched_vendor_name,
        alert_id=alert.id,
        event_id=event.id
    )

# ============= VENDOR ENDPOINTS =============

@router.post("/vendors")
async def create_watchtower_vendor(
    request: Request,
    vendor_data: dict,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Shortcut to create a vendor from Watchtower."""
    from app.api.vendors import VendorCreate, VendorResponse
    _require_role(user_context, Role.OPERATOR)
    vc = VendorCreate(**vendor_data)
    
    vendor = Vendor(
        organization_id=user_context["org_id"],
        name=vc.name,
        vendor_code=vc.vendor_code,
        vendor_type=vc.vendor_type,
        duns_number=vc.duns_number,
        address=vc.address,
        country=vc.country,
        contact_email=vc.contact_email,
        contact_phone=vc.contact_phone,
        notes=vc.notes,
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    
    return VendorResponse(
        id=vendor.id,
        name=vendor.name,
        vendor_code=vendor.vendor_code,
        vendor_type=vendor.vendor_type,
        duns_number=vendor.duns_number,
        address=vendor.address,
        country=vendor.country,
        contact_email=vendor.contact_email,
        contact_phone=vendor.contact_phone,
        risk_score=vendor.risk_score,
        risk_level=get_risk_level_str(vendor.risk_level),
        is_approved=vendor.is_approved,
        approval_date=vendor.approval_date,
        last_audit_date=vendor.last_audit_date,
        notes=vendor.notes,
        created_at=vendor.created_at,
        facility_count=0,
        alert_count=0,
    )

@router.get("/vendors")
async def list_watchtower_vendors(
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """List vendors for Watchtower dropdowns."""
    from app.api.vendors import list_vendors
    return await list_vendors(user_context=user_context, db=db)


@router.get("/events", response_model=List[EventResponse])
async def list_events(
    event_type: Optional[str] = Query(None, description="Filter by type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """List Watchtower events."""
    query = db.query(WatchtowerEvent)
    
    if event_type:
        query = query.filter(WatchtowerEvent.event_type == event_type)
    
    if severity:
        query = query.filter(WatchtowerEvent.severity == RiskLevel(severity))
    
    events = query.order_by(desc(WatchtowerEvent.created_at)).offset(offset).limit(limit).all()
    
    return [
        EventResponse(
            id=e.id,
            event_type=e.event_type,
            source=e.source,
            external_id=e.external_id,
            title=e.title,
            description=e.description,
            severity=e.severity.value if isinstance(e.severity, RiskLevel) else (e.severity if e.severity else "medium"),
            affected_products=e.affected_products,
            affected_companies=e.affected_companies,
            event_date=e.event_date,
            source_url=e.source_url,
            created_at=e.created_at,
        )
        for e in events
    ]


@router.get("/alerts", response_model=List[AlertResponse])
async def list_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity"),
    acknowledged: Optional[bool] = Query(None, description="Filter by acknowledgement status"),
    vendor_id: Optional[int] = Query(None, description="Filter by vendor"),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """List alerts for current organization."""
    query = db.query(WatchtowerAlert).filter(
        WatchtowerAlert.organization_id == user_context["org_id"]
    )
    
    if severity:
        query = query.filter(WatchtowerAlert.severity == RiskLevel(severity))
    
    if acknowledged is not None:
        query = query.filter(WatchtowerAlert.is_acknowledged == acknowledged)
    
    if vendor_id:
        query = query.filter(WatchtowerAlert.vendor_id == vendor_id)
    
    alerts = query.order_by(desc(WatchtowerAlert.created_at)).offset(offset).limit(limit).all()
    
    result = []
    for a in alerts:
        event_data = None
        if a.event:
            event_data = EventResponse(
                id=a.event.id,
                event_type=a.event.event_type,
                source=a.event.source,
                external_id=a.event.external_id,
                title=a.event.title,
                description=a.event.description,
                severity=a.event.severity.value if isinstance(a.event.severity, RiskLevel) else (a.event.severity if a.event.severity else "medium"),
                affected_products=a.event.affected_products,
                affected_companies=a.event.affected_companies,
                event_date=a.event.event_date,
                source_url=a.event.source_url,
                created_at=a.event.created_at,
            )
        
        result.append(AlertResponse(
            id=a.id,
            event_id=a.event_id,
            vendor_id=a.vendor_id,
            vendor_name=a.vendor.name if a.vendor else None,
            facility_id=a.facility_id,
            facility_name=a.facility.name if a.facility else None,
            severity=a.severity.value if isinstance(a.severity, RiskLevel) else (a.severity if a.severity else "medium"),
            is_acknowledged=a.is_acknowledged,
            acknowledged_at=a.acknowledged_at,
            notes=a.notes,
            created_at=a.created_at,
            event=event_data,
        ))
    
    return result


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    request: Request,
    data: AlertAcknowledge,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Acknowledge an alert."""
    _require_role(user_context, Role.OPERATOR)
    alert = db.query(WatchtowerAlert).filter(
        WatchtowerAlert.id == alert_id,
        WatchtowerAlert.organization_id == user_context["org_id"]
    ).first()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.is_acknowledged = True
    alert.acknowledged_by = int(user_context["sub"])
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.notes = data.notes
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="acknowledge_alert",
        entity_type="watchtower_alert",
        entity_id=alert_id,
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    
    return {"message": "Alert acknowledged"}


@router.post("/recalculate-risk")
async def recalculate_risk(
    request: Request,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Trigger risk recalculation for all vendors and facilities."""
    _require_role(user_context, Role.OPERATOR)
    org_id = user_context["org_id"]
    
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
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=org_id,
        action="recalculate_risk",
        entity_type="watchtower",
        details={"vendors_updated": len(vendors), "facilities_updated": len(facilities)},
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    
    return {
        "message": "Risk scores recalculated",
        "vendors_updated": len(vendors),
        "facilities_updated": len(facilities),
    }


# ============= LIVE FEED ENDPOINTS =============

class FeedItemResponse(BaseModel):
    id: int
    source: str
    external_id: str
    title: str
    url: Optional[str]
    published_at: Optional[datetime]
    summary: Optional[str]
    category: Optional[str]
    created_at: datetime
    
    class Config:
        orm_mode = True


class SourceResponse(BaseModel):
    source_id: str
    source_name: str
    category: str
    last_success_at: Optional[datetime]
    last_error_at: Optional[datetime]
    last_error_message: Optional[str]
    last_run_at: Optional[datetime]
    # Enhanced tracking fields
    last_http_status: Optional[int]
    items_fetched: Optional[int]
    items_saved: Optional[int]


class FeedSummaryResponse(BaseModel):
    total_items: int
    by_source: dict
    last_sync_at: Optional[str]
    all_sources_healthy: bool
    sources_count: int
    # Also include existing risk summary
    total_vendors: int
    high_risk_vendors: int
    active_alerts: int


@router.get("/feed", response_model=List[FeedItemResponse])
async def get_live_feed(
    source: Optional[str] = Query(None, description="Filter by source ID"),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """
    Get live feed items from FDA and other external sources.
    Items are persisted from RSS/API feeds.
    """
    from app.db.models import WatchtowerItem
    from sqlalchemy import desc
    
    query = db.query(WatchtowerItem)
    
    if source:
        query = query.filter(WatchtowerItem.source == source)
    
    items = query.order_by(desc(WatchtowerItem.published_at)).offset(offset).limit(limit).all()
    
    return [
        FeedItemResponse(
            id=item.id,
            source=item.source,
            external_id=item.external_id,
            title=item.title,
            url=item.url,
            published_at=item.published_at,
            summary=item.summary,
            category=item.category,
            created_at=item.created_at,
        )
        for item in items
    ]


@router.get("/sources", response_model=List[SourceResponse])
async def get_feed_sources(
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """
    List available feed sources with their sync status.
    """
    from app.services.watchtower.feed_service import list_providers, get_sync_status
    
    providers = list_providers()
    result = []
    
    for p in providers:
        status = get_sync_status(db, p["source_id"])
        result.append(SourceResponse(
            source_id=p["source_id"],
            source_name=p["source_name"],
            category=p["category"],
            last_success_at=status.last_success_at if status else None,
            last_error_at=status.last_error_at if status else None,
            last_error_message=status.last_error_message if status else None,
            last_run_at=status.last_run_at if status else None,
            last_http_status=status.last_http_status if status else None,
            items_fetched=status.items_fetched if status else None,
            items_saved=status.items_saved if status else None,
        ))
    
    return result


# Alias for /sources - some UI code may reference /feedsources
@router.get("/feedsources", response_model=List[SourceResponse])
async def get_feed_sources_alias(
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """
    Alias for /sources - List available feed sources with their sync status.
    """
    return await get_feed_sources(user_context=user_context, db=db)


@router.post("/sync")
async def trigger_sync(
    request: Request,
    source: Optional[str] = Query(None, description="Specific source to sync, or all if omitted"),
    force: bool = Query(False, description="Force fresh fetch, ignoring cache"),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """
    Trigger a sync of live feed data from external sources.
    Admin-only endpoint.

    Returns:
        HTTP 200 with JSON:
            - status: "ok" (success or partial success)
            - degraded: boolean (true if some sources failed)
            - results: array of per-source results
            - total_items_added: total new items persisted
        HTTP 502 if ALL sources fail
    """
    from app.services.watchtower.feed_service import sync_provider, sync_all_providers
    from fastapi.responses import JSONResponse

    # Check if user has admin role
    role = user_context.get("role", Role.VIEWER)
    if isinstance(role, str):
        try:
            role = Role(role)
        except ValueError:
            role = Role.VIEWER
    if role not in [Role.ADMIN, Role.OWNER]:
        raise HTTPException(status_code=403, detail="Only admins can trigger sync")

    logger.info(f"Sync triggered by user={user_context.get('sub')}, source={source or 'all'}, force={force}")

    try:
        if source:
            # Single source sync
            result = await sync_provider(source, db, force=force)
            response_data = {
                "status": "ok" if result.get("success") else "error",
                "degraded": not result.get("success"),
                "results": [result],
                "total_items_added": result.get("items_added", 0),
                "sources_succeeded": 1 if result.get("success") else 0,
                "sources_failed": 0 if result.get("success") else 1,
            }
        else:
            # All sources sync - sync_all_providers returns the structured response
            response_data = await sync_all_providers(db, force=force)

    except Exception as e:
        # Catch any unexpected errors during sync and return a structured response
        logger.error(f"Unexpected error during sync: {e}", exc_info=True)
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

    # Write audit log in a separate try block to avoid affecting the sync response
    try:
        # Ensure clean session state before audit log
        if db.is_active:
            try:
                db.rollback()
            except Exception:
                pass

        audit_log = AuditLog(
            user_id=int(user_context["sub"]),
            organization_id=user_context["org_id"],
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
            ip_address=request.client.host if request.client else None,
        )
        db.add(audit_log)
        db.commit()
    except Exception as audit_err:
        logger.error(f"Failed to write audit log for sync: {audit_err}")
        try:
            db.rollback()
        except Exception:
            pass

    # If ALL sources failed, return 502 with the errors
    if response_data.get("status") == "error" and response_data.get("sources_succeeded", 0) == 0:
        logger.error(f"All sync sources failed")
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "degraded": True,
                "detail": "All feed sources failed",
                "results": response_data.get("results", []),
                "total_items_added": 0,
            }
        )

    # Return 200 for success or partial success (degraded)
    return response_data


@router.get("/feed/summary")
async def get_feed_summary(
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """
    Get summary of live feed including counts and sync status.
    """
    from app.services.watchtower.feed_service import get_feed_summary as feed_summary
    from app.db.models import WatchtowerItem, WatchtowerSyncStatus
    
    # Get feed summary
    summary = feed_summary(db)
    
    # Get sync statuses for detail
    sync_statuses = db.query(WatchtowerSyncStatus).all()
    
    sources_detail = []
    for status in sync_statuses:
        sources_detail.append({
            "source": status.source,
            "last_success_at": status.last_success_at.isoformat() if status.last_success_at else None,
            "last_error_at": status.last_error_at.isoformat() if status.last_error_at else None,
            "last_error_message": status.last_error_message,
            "healthy": status.last_error_at is None or (
                status.last_success_at and status.last_success_at > status.last_error_at
            ),
        })
    
    # Also include org-level stats
    org_id = user_context["org_id"]
    vendors = db.query(Vendor).filter(Vendor.organization_id == org_id).all()
    active_alerts = db.query(WatchtowerAlert).filter(
        WatchtowerAlert.organization_id == org_id,
        WatchtowerAlert.status == WatchtowerAlertStatus.ACTIVE
    ).count()
    
    return {
        **summary,
        "sources_detail": sources_detail,
        "total_vendors": len(vendors),
        "high_risk_vendors": len([v for v in vendors if v.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]]),
        "active_alerts": active_alerts,
    }
