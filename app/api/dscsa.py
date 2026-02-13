"""
DSCSA EPCIS API routes - Serialization and track-and-trace.
"""
from typing import List, Optional
from datetime import datetime
import hashlib
import os
import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.db.models import (
    EPCISUpload, EPCISEvent, EPCISIssue, 
    AuditLog, EPCISValidationStatus, RiskLevel
)
from app.core.rbac import require_operator, get_current_user_context
from app.core.config import settings
from app.services.epcis_parse import parse_epcis_file
from app.services.epcis_validate import validate_epcis_events, detect_chain_breaks

router = APIRouter(prefix="/api/dscsa", tags=["DSCSA"])


# ============= SCHEMAS =============

class UploadResponse(BaseModel):
    id: int
    filename: str
    file_size: int
    validation_status: str
    event_count: int
    chain_break_count: int
    created_at: datetime
    validated_at: Optional[datetime]
    
    class Config:
        orm_mode = True


class UploadDetailResponse(UploadResponse):
    validation_results: Optional[dict]
    issues: List[dict]
    events: List[dict]


class IssueResponse(BaseModel):
    id: int
    issue_type: str
    severity: str
    field_path: Optional[str]
    message: str
    event_index: Optional[int]
    suggested_fix: Optional[str]
    
    class Config:
        orm_mode = True


# ============= ROUTES =============

@router.get("/uploads", response_model=List[UploadResponse])
async def list_uploads(
    status: Optional[str] = Query(None, description="Filter by validation status"),
    limit: int = Query(50, le=100),
    offset: int = Query(0),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """List EPCIS uploads for current organization."""
    query = db.query(EPCISUpload).filter(
        EPCISUpload.organization_id == user_context["org_id"]
    )
    
    if status:
        query = query.filter(EPCISUpload.validation_status == EPCISValidationStatus(status))
    
    uploads = query.order_by(desc(EPCISUpload.created_at)).offset(offset).limit(limit).all()
    
    return [
        UploadResponse(
            id=u.id,
            filename=u.filename,
            file_size=u.file_size or 0,
            validation_status=u.validation_status.value if u.validation_status else "pending",
            event_count=u.event_count or 0,
            chain_break_count=u.chain_break_count or 0,
            created_at=u.created_at,
            validated_at=u.validated_at,
        )
        for u in uploads
    ]


@router.post("/upload", response_model=UploadDetailResponse)
async def upload_epcis_file(
    request: Request,
    file: UploadFile = File(...),
    project_id: Optional[int] = None,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """Upload and validate an EPCIS file (JSON or XML)."""
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    ext = file.filename.lower().split('.')[-1]
    if ext not in ['json', 'xml']:
        raise HTTPException(status_code=400, detail="File must be JSON or XML")
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    if file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large")
    
    # Calculate hash
    file_hash = hashlib.sha256(content).hexdigest()
    
    # Save file
    upload_dir = os.path.join(settings.UPLOAD_DIR, "epcis")
    os.makedirs(upload_dir, exist_ok=True)
    
    file_path = os.path.join(upload_dir, f"{file_hash}_{file.filename}")
    with open(file_path, 'wb') as f:
        f.write(content)
    
    # Create upload record
    upload = EPCISUpload(
        organization_id=user_context["org_id"],
        project_id=project_id,
        uploaded_by=int(user_context["sub"]),
        filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        file_hash=file_hash,
        content_type="json" if ext == "json" else "xml",
        validation_status=EPCISValidationStatus.PENDING
    )
    db.add(upload)
    db.flush()
    
    # Parse EPCIS file
    try:
        events = parse_epcis_file(content.decode('utf-8'), ext)
    except Exception as e:
        upload.validation_status = EPCISValidationStatus.INVALID
        upload.validation_results = {"error": str(e)}
        db.commit()
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")
    
    # Store parsed events
    for idx, event_data in enumerate(events):
        event = EPCISEvent(
            upload_id=upload.id,
            event_type=event_data.get("eventType"),
            action=event_data.get("action"),
            event_time=event_data.get("eventTime"),
            event_timezone=event_data.get("eventTimeZoneOffset"),
            biz_step=event_data.get("bizStep"),
            disposition=event_data.get("disposition"),
            read_point=event_data.get("readPoint"),
            biz_location=event_data.get("bizLocation"),
            epc_list=event_data.get("epcList"),
            quantity_list=event_data.get("quantityList"),
            source_list=event_data.get("sourceList"),
            destination_list=event_data.get("destinationList"),
            raw_event=event_data,
        )
        db.add(event)
    
    upload.event_count = len(events)
    
    # Validate events
    validation_issues = validate_epcis_events(events)
    
    # Detect chain breaks
    chain_breaks = detect_chain_breaks(events)
    upload.chain_break_count = len(chain_breaks)
    
    # Store issues
    all_issues = validation_issues + chain_breaks
    for issue_data in all_issues:
        issue = EPCISIssue(
            upload_id=upload.id,
            issue_type=issue_data["type"],
            severity=RiskLevel(issue_data.get("severity", "medium")),
            field_path=issue_data.get("field_path"),
            message=issue_data["message"],
            event_index=issue_data.get("event_index"),
            suggested_fix=issue_data.get("suggested_fix"),
        )
        db.add(issue)
    
    # Determine validation status
    if any(i["severity"] == "critical" for i in all_issues):
        upload.validation_status = EPCISValidationStatus.INVALID
    elif chain_breaks:
        upload.validation_status = EPCISValidationStatus.CHAIN_BREAK
    elif all_issues:
        upload.validation_status = EPCISValidationStatus.VALID  # Valid with warnings
    else:
        upload.validation_status = EPCISValidationStatus.VALID
    
    upload.validated_at = datetime.utcnow()
    upload.validation_results = {
        "total_events": len(events),
        "issues_count": len(all_issues),
        "chain_breaks_count": len(chain_breaks),
    }
    
    # Audit log
    audit_log = AuditLog(
        user_id=int(user_context["sub"]),
        organization_id=user_context["org_id"],
        action="upload_epcis",
        entity_type="epcis_upload",
        entity_id=upload.id,
        details={
            "filename": file.filename,
            "status": upload.validation_status.value,
            "events": len(events),
            "issues": len(all_issues),
        },
        ip_address=request.client.host if request.client else None,
    )
    db.add(audit_log)
    db.commit()
    db.refresh(upload)
    
    return UploadDetailResponse(
        id=upload.id,
        filename=upload.filename,
        file_size=upload.file_size or 0,
        validation_status=upload.validation_status.value,
        event_count=upload.event_count or 0,
        chain_break_count=upload.chain_break_count or 0,
        created_at=upload.created_at,
        validated_at=upload.validated_at,
        validation_results=upload.validation_results,
        issues=[
            {
                "id": i.id,
                "type": i.issue_type,
                "severity": i.severity.value if i.severity else "medium",
                "field_path": i.field_path,
                "message": i.message,
                "event_index": i.event_index,
                "suggested_fix": i.suggested_fix,
            }
            for i in upload.issues
        ],
        events=[
            {
                "id": e.id,
                "event_type": e.event_type,
                "action": e.action,
                "event_time": e.event_time.isoformat() if e.event_time else None,
                "biz_step": e.biz_step,
                "epc_list": e.epc_list,
            }
            for e in upload.events
        ],
    )

# Alias for requested path /api/dscsa/epcis/upload
@router.post("/epcis/upload", response_model=UploadDetailResponse)
async def upload_epcis_file_alias(
    request: Request,
    file: UploadFile = File(...),
    project_id: Optional[int] = None,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    return await upload_epcis_file(request, file, project_id, user_context, db)

@router.get("/epcis/uploads", response_model=List[UploadResponse])
async def list_uploads_alias(
    status: Optional[str] = Query(None),
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    return await list_uploads(status, user_context=user_context, db=db)

@router.get("/epcis/uploads/{upload_id}", response_model=UploadDetailResponse)
async def get_upload_detail_alias(
    upload_id: int,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    return await get_upload_detail(upload_id, user_context, db)


@router.get("/uploads/{upload_id}", response_model=UploadDetailResponse)
async def get_upload_detail(
    upload_id: int,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Get detailed upload information."""
    upload = db.query(EPCISUpload).filter(
        EPCISUpload.id == upload_id,
        EPCISUpload.organization_id == user_context["org_id"]
    ).first()
    
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    return UploadDetailResponse(
        id=upload.id,
        filename=upload.filename,
        file_size=upload.file_size or 0,
        validation_status=upload.validation_status.value if upload.validation_status else "pending",
        event_count=upload.event_count or 0,
        chain_break_count=upload.chain_break_count or 0,
        created_at=upload.created_at,
        validated_at=upload.validated_at,
        validation_results=upload.validation_results,
        issues=[
            {
                "id": i.id,
                "type": i.issue_type,
                "severity": i.severity.value if i.severity else "medium",
                "field_path": i.field_path,
                "message": i.message,
                "event_index": i.event_index,
                "suggested_fix": i.suggested_fix,
            }
            for i in upload.issues
        ],
        events=[
            {
                "id": e.id,
                "event_type": e.event_type,
                "action": e.action,
                "event_time": e.event_time.isoformat() if e.event_time else None,
                "biz_step": e.biz_step,
                "epc_list": e.epc_list,
            }
            for e in upload.events
        ],
    )


@router.get("/uploads/{upload_id}/audit-packet")
async def download_audit_packet(
    upload_id: int,
    user_context: dict = Depends(get_current_user_context),
    db: Session = Depends(get_db)
):
    """Download complete audit packet as JSON bundle."""
    upload = db.query(EPCISUpload).filter(
        EPCISUpload.id == upload_id,
        EPCISUpload.organization_id == user_context["org_id"]
    ).first()
    
    if not upload:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    audit_packet = {
        "generated_at": datetime.utcnow().isoformat(),
        "upload": {
            "id": upload.id,
            "filename": upload.filename,
            "file_hash": upload.file_hash,
            "file_size": upload.file_size,
            "uploaded_at": upload.created_at.isoformat(),
            "validation_status": upload.validation_status.value if upload.validation_status else "pending",
            "validated_at": upload.validated_at.isoformat() if upload.validated_at else None,
        },
        "validation_summary": upload.validation_results,
        "events": [
            {
                "event_type": e.event_type,
                "action": e.action,
                "event_time": e.event_time.isoformat() if e.event_time else None,
                "event_timezone": e.event_timezone,
                "biz_step": e.biz_step,
                "disposition": e.disposition,
                "read_point": e.read_point,
                "biz_location": e.biz_location,
                "epc_list": e.epc_list,
                "quantity_list": e.quantity_list,
                "source_list": e.source_list,
                "destination_list": e.destination_list,
            }
            for e in upload.events
        ],
        "issues": [
            {
                "type": i.issue_type,
                "severity": i.severity.value if i.severity else "medium",
                "field_path": i.field_path,
                "message": i.message,
                "event_index": i.event_index,
                "suggested_fix": i.suggested_fix,
            }
            for i in upload.issues
        ],
    }
    
    return JSONResponse(
        content=audit_packet,
        headers={
            "Content-Disposition": f'attachment; filename="audit_packet_{upload_id}.json"'
        }
    )


@router.get("/health")
async def dscsa_health(
    db: Session = Depends(get_db)
):
    """
    DSCSA module health check.
    Returns status and data counts.
    """
    # Get upload count
    upload_count = db.query(EPCISUpload).count()
    event_count = db.query(EPCISEvent).count()
    issue_count = db.query(EPCISIssue).count()
    
    return {
        "status": "healthy",
        "module": "dscsa",
        "upload_count": upload_count,
        "event_count": event_count,
        "issue_count": issue_count,
        "message": f"DSCSA module ready with {upload_count} uploads processed"
    }

