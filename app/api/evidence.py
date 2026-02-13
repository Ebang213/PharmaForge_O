"""
Evidence API - Document upload and retrieval for Knowledge Base.

Evidence processing flow:
1. Upload starts → status = PENDING
2. Text extraction begins → status = PROCESSING
3. Text extraction succeeds → status = PROCESSED, processed_at set
4. Text extraction fails → status = FAILED, error_message set
"""
import hashlib
import os
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_

from app.db.session import get_db
from app.db.models import Evidence, EvidenceStatus, AuditLog
from app.core.rbac import require_viewer, require_operator
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/evidence", tags=["Evidence"])


# ============= SCHEMAS =============

class EvidenceListItem(BaseModel):
    id: int
    filename: str
    sha256: str
    content_type: Optional[str]
    status: str  # "processed" or "pending"
    source: Optional[str]  # "copilot" or "watchtower"
    created_at: datetime
    uploaded_by: int
    
    class Config:
        from_attributes = True


class EvidenceDetail(EvidenceListItem):
    extracted_text: Optional[str]


class EvidenceUploadResponse(BaseModel):
    id: int
    filename: str
    sha256: str
    status: str
    created_at: datetime
    message: str


# ============= TEXT EXTRACTION =============

def extract_text_from_pdf(content: bytes) -> str:
    """Extract text from PDF using pypdf."""
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        return "\n\n".join(text_parts)
    except Exception as e:
        return f"[PDF extraction failed: {str(e)}]"


def extract_text_from_file(content: bytes, content_type: str, filename: str) -> str:
    """Extract text based on file type."""
    if content_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return extract_text_from_pdf(content)
    elif content_type in ("text/plain",) or filename.lower().endswith(".txt"):
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                return content.decode("latin-1")
            except:
                return "[Failed to decode text file]"
    else:
        # Try as text
        try:
            return content.decode("utf-8")
        except:
            return "[Unsupported file format]"


# ============= ENDPOINTS =============

@router.post("", response_model=EvidenceUploadResponse)
async def upload_evidence(
    request: Request,
    file: UploadFile = File(...),
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """
    Upload a new evidence document (PDF/TXT).
    
    The file is:
    1. Hashed (SHA256) for deduplication
    2. Stored on disk
    3. Text is extracted immediately
    4. A database record is created
    """
    # Validate file type
    allowed_extensions = {".pdf", ".txt"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"File type not allowed. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Read and hash
    content = await file.read()
    sha256 = hashlib.sha256(content).hexdigest()
    
    # Check for duplicate
    existing = db.query(Evidence).filter(
        Evidence.organization_id == user_context["org_id"],
        Evidence.sha256 == sha256,
        or_(Evidence.source.is_(None), Evidence.source != "watchtower"),
        ~Evidence.alerts.any()
    ).first()
    
    if existing:
        # Return existing evidence status
        status_str = existing.status.value if hasattr(existing.status, 'value') else str(existing.status or "pending")
        return EvidenceUploadResponse(
            id=existing.id,
            filename=existing.filename,
            sha256=existing.sha256,
            status=status_str,
            created_at=existing.uploaded_at,
            message="File already exists (duplicate SHA256)"
        )

    # Save file
    storage_dir = os.path.join(settings.UPLOAD_DIR, "evidence")
    os.makedirs(storage_dir, exist_ok=True)
    storage_path = os.path.join(storage_dir, f"{sha256}_{file.filename}")

    with open(storage_path, "wb") as f:
        f.write(content)

    # Create Evidence record with PENDING status
    evidence = Evidence(
        organization_id=user_context["org_id"],
        filename=file.filename or "unnamed",
        content_type=file.content_type,
        storage_path=storage_path,
        sha256=sha256,
        uploaded_by=int(user_context["sub"]),
        source="copilot",
        status=EvidenceStatus.PENDING
    )
    db.add(evidence)
    db.flush()  # Get ID before processing

    # Transition to PROCESSING
    evidence.status = EvidenceStatus.PROCESSING
    db.flush()

    # Extract text
    try:
        extracted_text = extract_text_from_file(content, file.content_type or "", file.filename or "")

        # Check if extraction was successful
        if extracted_text and not extracted_text.startswith("["):
            # Success - transition to PROCESSED
            evidence.extracted_text = extracted_text
            evidence.status = EvidenceStatus.PROCESSED
            evidence.processed_at = datetime.utcnow()
            status_str = "processed"
            message = "File uploaded and processed successfully"
        elif extracted_text and extracted_text.startswith("["):
            # Extraction failed with error message
            evidence.extracted_text = extracted_text
            evidence.status = EvidenceStatus.FAILED
            evidence.error_message = extracted_text
            evidence.processed_at = datetime.utcnow()
            status_str = "failed"
            message = f"File uploaded but text extraction failed: {extracted_text}"
        else:
            # Empty extraction
            evidence.status = EvidenceStatus.PROCESSED
            evidence.processed_at = datetime.utcnow()
            status_str = "processed"
            message = "File uploaded and processed (no text content)"
    except Exception as e:
        # Exception during extraction - transition to FAILED
        evidence.status = EvidenceStatus.FAILED
        evidence.error_message = str(e)
        evidence.processed_at = datetime.utcnow()
        status_str = "failed"
        message = f"File uploaded but processing failed: {str(e)}"

    db.commit()
    db.refresh(evidence)

    # Create audit log entry for evidence upload
    audit_log = AuditLog(
        organization_id=user_context["org_id"],
        user_id=int(user_context["sub"]),
        action="evidence_uploaded",
        entity_type="evidence",
        entity_id=evidence.id,
        details={
            "filename": evidence.filename,
            "sha256": evidence.sha256,
            "content_type": evidence.content_type,
            "status": status_str,
            "source": "copilot"
        },
        ip_address=request.client.host if request.client else None
    )
    db.add(audit_log)
    db.commit()

    logger.info(f"Evidence uploaded: {evidence.filename} (ID: {evidence.id}, status: {status_str})")

    return EvidenceUploadResponse(
        id=evidence.id,
        filename=evidence.filename,
        sha256=evidence.sha256,
        status=status_str,
        created_at=evidence.uploaded_at,
        message=message
    )


@router.get("", response_model=List[EvidenceListItem])
async def list_evidence(
    limit: int = 20,
    user_context: dict = Depends(require_viewer),
    db: Session = Depends(get_db)
):
    """
    List the most recent evidence uploads.
    Returns the last 20 uploads by default.
    """
    evidence_list = db.query(Evidence).filter(
        Evidence.organization_id == user_context["org_id"],
        or_(Evidence.source.is_(None), Evidence.source != "watchtower"),
        ~Evidence.alerts.any()
    ).order_by(desc(Evidence.uploaded_at)).limit(limit).all()
    
    return [
        EvidenceListItem(
            id=e.id,
            filename=e.filename,
            sha256=e.sha256,
            content_type=e.content_type,
            status=e.status.value if hasattr(e.status, 'value') else str(e.status or "pending"),
            source=e.source or "copilot",
            created_at=e.uploaded_at,
            uploaded_by=e.uploaded_by
        )
        for e in evidence_list
    ]


@router.get("/{evidence_id}", response_model=EvidenceDetail)
async def get_evidence(
    evidence_id: int,
    user_context: dict = Depends(require_viewer),
    db: Session = Depends(get_db)
):
    """Get details of a specific evidence document."""
    evidence = db.query(Evidence).filter(
        Evidence.id == evidence_id,
        Evidence.organization_id == user_context["org_id"],
        or_(Evidence.source.is_(None), Evidence.source != "watchtower"),
        ~Evidence.alerts.any()
    ).first()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    return EvidenceDetail(
        id=evidence.id,
        filename=evidence.filename,
        sha256=evidence.sha256,
        content_type=evidence.content_type,
        status=evidence.status.value if hasattr(evidence.status, 'value') else str(evidence.status or "pending"),
        source=evidence.source or "copilot",
        created_at=evidence.uploaded_at,
        uploaded_by=evidence.uploaded_by,
        extracted_text=evidence.extracted_text
    )
