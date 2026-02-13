"""
Risk Findings API - Golden Workflow endpoints.
Analyzes evidence documents to extract compliance findings with CFR references.
Persists all workflow data to database for reliable audit packet export.
"""
from typing import List, Optional
from datetime import datetime
import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.db.models import (
    Evidence, EvidenceStatus, AuditLog, Vendor, WatchtowerItem, WatchtowerAlert, Facility,
    WorkflowRun, WorkflowRunStatus, RiskFindingRecord, ActionPlanRecord,
    WatchtowerSyncStatus
)
from app.core.rbac import require_viewer, require_operator
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/risk", tags=["Risk Findings"])


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


# ============= SCHEMAS =============

class RiskFindingCreate(BaseModel):
    """Individual risk finding."""
    title: str
    description: str
    severity: str  # LOW, MEDIUM, HIGH
    cfr_refs: Optional[List[str]] = []
    citations: Optional[List[str]] = []
    entities: Optional[List[str]] = []  # vendors/products


class RiskFinding(RiskFindingCreate):
    """Risk finding response."""
    id: int
    evidence_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class FindingsRunResponse(BaseModel):
    """Response from running findings extraction."""
    evidence_id: int
    findings: List[RiskFinding]
    message: str


class ActionItem(BaseModel):
    """Action item in an action plan."""
    title: str
    description: str
    priority: str  # HIGH, MEDIUM, LOW
    owner: Optional[str] = None
    deadline: Optional[str] = None


class ActionPlanRequest(BaseModel):
    """Request to generate an action plan."""
    evidence_id: int
    findings: List[dict]
    watchtower_summary: Optional[dict] = None
    vendor_risks: Optional[List[dict]] = None


class ActionPlanResponse(BaseModel):
    """Generated action plan."""
    top_actions: List[ActionItem]
    rationale: str
    owners: List[str]
    deadlines: List[str]
    linked_evidence: int
    audit_entries: List[dict]
    workflow_run_id: Optional[int] = None


class AuditPacketExport(BaseModel):
    """Full audit packet for export."""
    evidence_metadata: dict
    findings: List[dict]
    watchtower_summary: Optional[dict]
    action_plan: Optional[dict]
    audit_log: List[dict]
    workflow_run_id: Optional[int] = None


class WorkflowRunResponse(BaseModel):
    """Response from running the complete workflow."""
    workflow_run_id: int
    evidence_id: int
    status: str
    findings_count: int
    correlations_count: int
    actions_count: int
    created_at: str
    message: str


# ============= CORRELATION SCHEMAS =============

class CorrelationRequest(BaseModel):
    """Request balance for correlation engine."""
    evidence_id: int
    findings: Optional[List[dict]] = None


class VendorMatch(BaseModel):
    """Matched vendor from correlation."""
    vendor_id: Optional[int] = None
    name: str
    match_basis: str  # "filename", "text_content", "finding"
    risk_score: Optional[float] = None
    risk_level: Optional[str] = None


class WatchtowerSnapshot(BaseModel):
    """Watchtower state snapshot for correlation."""
    total_feed_items: int
    active_alerts: int
    sources_status: List[dict]
    top_items: List[dict]  # Top 5 recent items
    timestamp: str


class CorrelationResult(BaseModel):
    """Full correlation result."""
    evidence_id: int
    watchtower_snapshot: WatchtowerSnapshot
    vendor_matches: List[VendorMatch]
    narrative: List[str]  # 3-5 bullet points
    correlation_timestamp: str


# ============= IN-MEMORY CACHE (for session state before persistence) =============
# These are now used as temporary cache; final data is persisted to DB
_findings_cache: dict = {}  # { evidence_id: [findings] } - temporary before workflow run
_correlations_cache: dict = {}  # { evidence_id: CorrelationResult } - temporary before workflow run
_finding_id_counter = [0]


def _next_finding_id():
    _finding_id_counter[0] += 1
    return _finding_id_counter[0]


# ============= MOCK FINDINGS GENERATOR =============

def _generate_mock_findings(text: str, evidence_id: int) -> List[dict]:
    """Generate mock findings based on document text."""
    findings = []
    text_lower = text.lower() if text else ""
    
    # Analyze text for common compliance issues
    if "temperature" in text_lower or "cold chain" in text_lower or "storage" in text_lower:
        findings.append({
            "id": _next_finding_id(),
            "evidence_id": evidence_id,
            "title": "Cold Chain Storage Compliance Gap",
            "description": "Document references temperature-sensitive storage. Verify compliance with 21 CFR 211.142 storage requirements.",
            "severity": "HIGH",
            "cfr_refs": ["21 CFR 211.142", "21 CFR 211.150"],
            "citations": ["'temperature' mentioned in source document"],
            "entities": [],
            "created_at": datetime.utcnow().isoformat()
        })
    
    if "cgmp" in text_lower or "gmp" in text_lower or "manufacturing" in text_lower:
        findings.append({
            "id": _next_finding_id(),
            "evidence_id": evidence_id,
            "title": "cGMP Documentation Review Required",
            "description": "Manufacturing processes referenced require cGMP compliance verification per 21 CFR Parts 210-211.",
            "severity": "MEDIUM",
            "cfr_refs": ["21 CFR 210", "21 CFR 211"],
            "citations": ["Manufacturing/cGMP terminology in document"],
            "entities": [],
            "created_at": datetime.utcnow().isoformat()
        })
    
    if "recall" in text_lower or "defect" in text_lower or "deviation" in text_lower:
        findings.append({
            "id": _next_finding_id(),
            "evidence_id": evidence_id,
            "title": "Product Quality Deviation Detected",
            "description": "Quality deviation or recall-related content found. Immediate investigation required per 21 CFR 211.192.",
            "severity": "HIGH",
            "cfr_refs": ["21 CFR 211.192", "21 CFR Part 7"],
            "citations": ["Quality deviation terminology detected"],
            "entities": [],
            "created_at": datetime.utcnow().isoformat()
        })
    
    if "supplier" in text_lower or "vendor" in text_lower:
        findings.append({
            "id": _next_finding_id(),
            "evidence_id": evidence_id,
            "title": "Supplier Qualification Assessment Needed",
            "description": "Supplier/vendor references found. Verify supplier qualification per 21 CFR 211.84.",
            "severity": "MEDIUM",
            "cfr_refs": ["21 CFR 211.84", "21 CFR 211.80"],
            "citations": ["Supplier/vendor references in document"],
            "entities": [],
            "created_at": datetime.utcnow().isoformat()
        })
    
    if "labeling" in text_lower or "label" in text_lower:
        findings.append({
            "id": _next_finding_id(),
            "evidence_id": evidence_id,
            "title": "Labeling Compliance Check Required",
            "description": "Labeling content detected. Verify compliance with 21 CFR 211.122-137 labeling requirements.",
            "severity": "MEDIUM",
            "cfr_refs": ["21 CFR 211.122", "21 CFR 211.125", "21 CFR 211.130"],
            "citations": ["Labeling terminology in document"],
            "entities": [],
            "created_at": datetime.utcnow().isoformat()
        })
    
    if "serialization" in text_lower or "dscsa" in text_lower or "traceability" in text_lower:
        findings.append({
            "id": _next_finding_id(),
            "evidence_id": evidence_id,
            "title": "DSCSA Serialization Compliance Required",
            "description": "Serialization/traceability content found. Ensure DSCSA compliance for product tracking.",
            "severity": "HIGH",
            "cfr_refs": ["DSCSA Section 582"],
            "citations": ["Serialization/DSCSA references in document"],
            "entities": [],
            "created_at": datetime.utcnow().isoformat()
        })
    
    # Always add at least one general finding
    if len(findings) < 3:
        findings.append({
            "id": _next_finding_id(),
            "evidence_id": evidence_id,
            "title": "General Document Compliance Review",
            "description": "Document requires review for general regulatory compliance. Consider 21 CFR Part 211 applicability.",
            "severity": "LOW",
            "cfr_refs": ["21 CFR 211"],
            "citations": ["General document review"],
            "entities": [],
            "created_at": datetime.utcnow().isoformat()
        })
    
    if len(findings) < 3:
        findings.append({
            "id": _next_finding_id(),
            "evidence_id": evidence_id,
            "title": "Record Retention Verification",
            "description": "Verify document retention policies align with 21 CFR 211.180 requirements.",
            "severity": "LOW",
            "cfr_refs": ["21 CFR 211.180"],
            "citations": ["Standard record retention check"],
            "entities": [],
            "created_at": datetime.utcnow().isoformat()
        })
    
    return findings[:10]  # Cap at 10 findings


def _generate_action_plan(findings: List[dict], watchtower_summary: Optional[dict], vendor_risks: Optional[List[dict]]) -> dict:
    """Generate mock action plan based on findings."""
    actions = []
    
    # High priority actions from HIGH severity findings
    high_findings = [f for f in findings if f.get("severity") == "HIGH"]
    for f in high_findings[:3]:
        actions.append({
            "title": f"Investigate: {f.get('title', 'Unknown issue')}",
            "description": f"Address finding: {f.get('description', '')}. Reference: {', '.join(f.get('cfr_refs', []))}",
            "priority": "HIGH",
            "owner": "Quality Assurance Lead",
            "deadline": "Within 48 hours"
        })
    
    # Medium priority actions
    medium_findings = [f for f in findings if f.get("severity") == "MEDIUM"]
    for f in medium_findings[:2]:
        actions.append({
            "title": f"Review: {f.get('title', 'Unknown issue')}",
            "description": f"Evaluate finding: {f.get('description', '')}",
            "priority": "MEDIUM",
            "owner": "Regulatory Affairs",
            "deadline": "Within 7 days"
        })
    
    # Add vendor-related action if vendor risks provided
    if vendor_risks:
        actions.append({
            "title": "Vendor Risk Mitigation",
            "description": f"Review {len(vendor_risks)} vendor(s) identified with elevated risk profiles.",
            "priority": "MEDIUM",
            "owner": "Supply Chain Manager",
            "deadline": "Within 14 days"
        })
    
    # Always add documentation action
    actions.append({
        "title": "Document Remediation Actions",
        "description": "Compile remediation documentation and update CAPA records.",
        "priority": "LOW",
        "owner": "Documentation Specialist",
        "deadline": "Ongoing"
    })
    
    rationale = (
        f"Action plan generated based on {len(findings)} compliance finding(s). "
        f"Prioritized {len(high_findings)} HIGH severity issue(s) requiring immediate attention. "
        f"{'Vendor risks incorporated into supply chain review.' if vendor_risks else ''}"
    )
    
    owners = list(set(a["owner"] for a in actions))
    deadlines = list(set(a["deadline"] for a in actions))
    
    return {
        "top_actions": actions,
        "rationale": rationale,
        "owners": owners,
        "deadlines": deadlines
    }


def _extract_vendor_candidates(text: str, filename: str, findings: List[dict]) -> List[str]:
    """Extract potential vendor/manufacturer names from text and findings."""
    candidates = set()
    
    # Common pharma company patterns
    company_patterns = [
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Pharma|Labs?|Laboratories|Inc\.?|Corp\.?|LLC|Ltd\.?))\b',
        r'\b([A-Z][A-Z]+\s+(?:Pharma|Labs?|Laboratories|Inc\.?|Corp\.?|LLC|Ltd\.?))\b',
    ]
    
    # Extract from text
    for pattern in company_patterns:
        matches = re.findall(pattern, text or "")
        candidates.update(matches)
    
    # Extract from filename (often contains vendor name)
    name_parts = re.split(r'[-_\s]+', filename.replace('.pdf', '').replace('.txt', ''))
    for part in name_parts:
        if len(part) > 3 and part[0].isupper():
            candidates.add(part)
    
    # Extract from findings entities
    for finding in findings:
        entities = finding.get("entities", [])
        candidates.update(entities)
    
    return list(candidates)[:10]  # Limit to 10 candidates


def _generate_correlation(
    evidence: "Evidence",
    findings: List[dict],
    db: Session,
    org_id: int
) -> dict:
    """
    Generate correlation between evidence/findings and Watchtower data.
    Fetches Watchtower state server-side (no frontend fetch required).
    """
    from sqlalchemy import desc
    
    # 1. Get Watchtower snapshot
    total_feed_items = db.query(WatchtowerItem).count()
    active_alerts = db.query(WatchtowerAlert).filter(
        WatchtowerAlert.organization_id == org_id,
        WatchtowerAlert.is_acknowledged == False
    ).count()
    
    # Get top 5 recent items
    recent_items = db.query(WatchtowerItem).order_by(
        desc(WatchtowerItem.published_at)
    ).limit(5).all()
    
    top_items = [
        {
            "id": item.id,
            "source": item.source,
            "title": item.title[:100] if item.title else "",
            "category": item.category,
            "published_at": item.published_at.isoformat() if item.published_at else None
        }
        for item in recent_items
    ]
    
    # Get sources status (simplified)
    from app.db.models import WatchtowerSyncStatus
    sync_statuses = db.query(WatchtowerSyncStatus).all()
    sources_status = [
        {
            "source": s.source,
            "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
            "healthy": s.last_error_at is None or (
                s.last_success_at and s.last_success_at > s.last_error_at
            )
        }
        for s in sync_statuses
    ]
    
    watchtower_snapshot = WatchtowerSnapshot(
        total_feed_items=total_feed_items,
        active_alerts=active_alerts,
        sources_status=sources_status,
        top_items=top_items,
        timestamp=datetime.utcnow().isoformat() + "Z"
    )
    
    # 2. Extract vendor candidates from evidence
    text = evidence.extracted_text or ""
    filename = evidence.filename or ""
    candidates = _extract_vendor_candidates(text, filename, findings)
    
    # 3. Match against Vendors table
    vendors = db.query(Vendor).filter(Vendor.organization_id == org_id).all()
    vendor_matches = []
    matched_ids = set()
    
    for v in vendors:
        v_name_lower = v.name.lower()
        for candidate in candidates:
            if candidate.lower() in v_name_lower or v_name_lower in candidate.lower():
                if v.id not in matched_ids:
                    vendor_matches.append(VendorMatch(
                        vendor_id=v.id,
                        name=v.name,
                        match_basis="text_content",
                        risk_score=v.risk_score,
                        risk_level=get_risk_level_str(v.risk_level)
                    ))
                    matched_ids.add(v.id)
    
    # Add unmatched candidates as potential vendors
    for candidate in candidates[:5]:
        already_matched = any(candidate.lower() in vm.name.lower() for vm in vendor_matches)
        if not already_matched and len(candidate) > 3:
            vendor_matches.append(VendorMatch(
                vendor_id=None,
                name=candidate,
                match_basis="unmatched_candidate",
                risk_score=None,
                risk_level=None
            ))
    
    # 4. Generate narrative bullets
    narrative = []
    
    high_findings = [f for f in findings if f.get("severity") == "HIGH"]
    if high_findings:
        narrative.append(f"🔴 {len(high_findings)} HIGH severity finding(s) require immediate attention.")
    
    if active_alerts > 0:
        narrative.append(f"⚠️ {active_alerts} active Watchtower alert(s) may indicate supply chain exposure.")
    
    matched_vendors = [vm for vm in vendor_matches if vm.vendor_id]
    if matched_vendors:
        high_risk = [vm for vm in matched_vendors if vm.risk_level in ("high", "critical")]
        if high_risk:
            narrative.append(f"🚨 {len(high_risk)} matched vendor(s) flagged as high/critical risk.")
        else:
            narrative.append(f"✓ {len(matched_vendors)} vendor(s) identified and tracked in your vendor registry.")
    
    if total_feed_items > 0:
        narrative.append(f"📡 Watchtower is monitoring {total_feed_items} FDA feed item(s) for correlation.")
    
    if not narrative:
        narrative.append("No significant correlations detected. Consider uploading more evidence or syncing Watchtower feeds.")
    
    return {
        "evidence_id": evidence.id,
        "watchtower_snapshot": watchtower_snapshot.dict(),
        "vendor_matches": [vm.dict() for vm in vendor_matches],
        "narrative": narrative,
        "correlation_timestamp": datetime.utcnow().isoformat() + "Z"
    }


# ============= ENDPOINTS =============

@router.post("/findings/run", response_model=FindingsRunResponse)
async def run_findings_extraction(
    request: Request,
    evidence_id: int = Query(..., description="Evidence document ID"),
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """
    Extract compliance findings from an evidence document.
    Produces 3-10 findings with CFR references and citations.
    """
    # Get evidence
    evidence = db.query(Evidence).filter(
        Evidence.id == evidence_id,
        Evidence.organization_id == user_context["org_id"]
    ).first()

    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    # Check evidence is processed
    evidence_status = evidence.status.value if hasattr(evidence.status, 'value') else str(evidence.status)
    if evidence_status != "processed":
        raise HTTPException(
            status_code=400,
            detail=f"Evidence is not processed (status: {evidence_status}). Only processed evidence can be analyzed."
        )

    if not evidence.extracted_text:
        raise HTTPException(status_code=400, detail="Evidence has no extracted text")

    # Generate findings
    findings = _generate_mock_findings(evidence.extracted_text, evidence_id)
    
    # Store findings
    _findings_cache[evidence_id] = findings
    
    # Create audit log entry
    audit_log = AuditLog(
        organization_id=user_context["org_id"],
        user_id=int(user_context["sub"]),
        action="findings_generated",
        entity_type="evidence",
        entity_id=evidence_id,
        details={"finding_count": len(findings)},
        ip_address=request.client.host if request.client else None
    )
    db.add(audit_log)
    db.commit()
    
    logger.info(f"Generated {len(findings)} findings for evidence {evidence_id}")
    
    return FindingsRunResponse(
        evidence_id=evidence_id,
        findings=[RiskFinding(**f) for f in findings],
        message=f"Generated {len(findings)} compliance findings"
    )


@router.get("/findings", response_model=List[RiskFinding])
async def get_findings(
    evidence_id: int = Query(..., description="Evidence document ID"),
    user_context: dict = Depends(require_viewer),
    db: Session = Depends(get_db)
):
    """
    Get stored findings for an evidence document.
    """
    # Verify evidence belongs to org
    evidence = db.query(Evidence).filter(
        Evidence.id == evidence_id,
        Evidence.organization_id == user_context["org_id"]
    ).first()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    findings = _findings_cache.get(evidence_id, [])
    return [RiskFinding(**f) for f in findings]


@router.post("/correlate", response_model=CorrelationResult)
async def correlate_risk(
    request: Request,
    correlation_request: CorrelationRequest,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """
    Correlate evidence and findings with Watchtower supply chain data.
    
    This endpoint fetches Watchtower data server-side (frontend does NOT need to fetch it).
    
    Returns:
    - watchtower_snapshot: Current state of FDA feeds, alerts, sources
    - vendor_matches: Vendors matched from evidence text/filename/findings
    - narrative: 3-5 bullet points explaining why this matters
    """
    evidence_id = correlation_request.evidence_id
    
    # Get evidence
    evidence = db.query(Evidence).filter(
        Evidence.id == evidence_id,
        Evidence.organization_id == user_context["org_id"]
    ).first()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    # Get findings (from request or from store)
    findings = correlation_request.findings
    if not findings:
        findings = _findings_cache.get(evidence_id, [])
    
    # Generate correlation
    correlation = _generate_correlation(evidence, findings, db, user_context["org_id"])
    
    # Store correlation
    _correlations_cache[evidence_id] = correlation
    
    # Audit log - use correlation_generated as the action name
    audit_log = AuditLog(
        organization_id=user_context["org_id"],
        user_id=int(user_context["sub"]),
        action="correlation_generated",
        entity_type="evidence",
        entity_id=evidence_id,
        details={
            "vendor_matches": len(correlation["vendor_matches"]),
            "active_alerts": correlation["watchtower_snapshot"]["active_alerts"],
            "findings_count": len(findings),
            "narrative_points": len(correlation["narrative"])
        },
        ip_address=request.client.host if request.client else None
    )
    db.add(audit_log)
    db.commit()
    
    logger.info(f"Generated correlation for evidence {evidence_id}")
    
    return CorrelationResult(**correlation)


@router.get("/correlation/{evidence_id}")
async def get_correlation(
    evidence_id: int,
    user_context: dict = Depends(require_viewer),
    db: Session = Depends(get_db)
):
    """Get stored correlation for an evidence document."""
    # Verify evidence belongs to org
    evidence = db.query(Evidence).filter(
        Evidence.id == evidence_id,
        Evidence.organization_id == user_context["org_id"]
    ).first()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")
    
    correlation = _correlations_cache.get(evidence_id)
    if not correlation:
        raise HTTPException(status_code=404, detail="No correlation found. Run /api/risk/correlate first.")
    
    return correlation


@router.post("/warcouncil/plan", response_model=ActionPlanResponse)
async def generate_action_plan_endpoint(
    request: Request,
    plan_request: ActionPlanRequest,
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """
    Generate an action plan from findings, watchtower summary, and vendor risks.

    This endpoint is called by the frontend when using the step-by-step workflow.
    For the full end-to-end workflow, use POST /api/risk/workflow/run instead.
    """
    evidence_id = plan_request.evidence_id
    org_id = user_context["org_id"]

    # Verify evidence exists and belongs to org
    evidence = db.query(Evidence).filter(
        Evidence.id == evidence_id,
        Evidence.organization_id == org_id
    ).first()

    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    # Get findings from request or from cache
    findings = plan_request.findings
    if not findings:
        findings = _findings_cache.get(evidence_id, [])

    # Convert vendor_risks to expected format
    vendor_risks = plan_request.vendor_risks or []

    # Generate action plan
    plan_data = _generate_action_plan(findings, plan_request.watchtower_summary, vendor_risks)

    # Get audit entries for this evidence
    audit_logs = db.query(AuditLog).filter(
        AuditLog.organization_id == org_id,
        AuditLog.entity_type == "evidence",
        AuditLog.entity_id == evidence_id
    ).order_by(AuditLog.timestamp).all()

    audit_entries = [
        {
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "action": log.action,
            "details": log.details
        }
        for log in audit_logs
    ]

    # Create audit log entry for plan generation
    audit_log = AuditLog(
        organization_id=org_id,
        user_id=int(user_context["sub"]),
        action="action_plan_generated",
        entity_type="evidence",
        entity_id=evidence_id,
        details={
            "findings_count": len(findings),
            "actions_count": len(plan_data.get("top_actions", []))
        },
        ip_address=request.client.host if request.client else None
    )
    db.add(audit_log)
    db.commit()

    logger.info(f"Generated action plan for evidence {evidence_id}")

    return ActionPlanResponse(
        top_actions=[ActionItem(**a) for a in plan_data.get("top_actions", [])],
        rationale=plan_data.get("rationale", ""),
        owners=plan_data.get("owners", []),
        deadlines=plan_data.get("deadlines", []),
        linked_evidence=evidence_id,
        audit_entries=audit_entries,
        workflow_run_id=None  # Step-by-step doesn't create a workflow run
    )


@router.post("/workflow/run", response_model=WorkflowRunResponse)
async def run_complete_workflow(
    request: Request,
    evidence_id: int = Query(..., description="Evidence document ID"),
    user_context: dict = Depends(require_operator),
    db: Session = Depends(get_db)
):
    """
    Run the complete Golden Workflow end-to-end:
    1. Validate evidence is processed
    2. Generate findings
    3. Generate correlation
    4. Generate action plan
    5. Persist everything to DB with workflow_run_id
    
    This creates a complete, auditable workflow run that can be exported.
    """
    org_id = user_context["org_id"]
    user_id = int(user_context["sub"])
    
    # Get evidence
    evidence = db.query(Evidence).filter(
        Evidence.id == evidence_id,
        Evidence.organization_id == org_id
    ).first()
    
    if not evidence:
        raise HTTPException(status_code=404, detail="Evidence not found")

    # Check evidence is processed
    evidence_status = evidence.status.value if hasattr(evidence.status, 'value') else str(evidence.status)
    if evidence_status == "pending":
        raise HTTPException(
            status_code=400,
            detail="Evidence is still pending processing. Please wait for processing to complete."
        )
    if evidence_status == "processing":
        raise HTTPException(
            status_code=400,
            detail="Evidence is currently being processed. Please wait for processing to complete."
        )
    if evidence_status == "failed":
        raise HTTPException(
            status_code=400,
            detail=f"Evidence processing failed: {evidence.error_message or 'Unknown error'}. Please upload a valid document."
        )

    if not evidence.extracted_text:
        raise HTTPException(
            status_code=400,
            detail="Evidence has no extracted text. Upload a PDF or TXT file with content."
        )
    
    # Create workflow run record
    workflow_run = WorkflowRun(
        organization_id=org_id,
        evidence_id=evidence_id,
        created_by=user_id,
        status=WorkflowRunStatus.RUNNING
    )
    db.add(workflow_run)
    db.flush()  # Get the ID
    
    try:
        # 1. Generate findings
        findings_data = _generate_mock_findings(evidence.extracted_text, evidence_id)
        
        # Persist findings to DB
        for f in findings_data:
            finding_record = RiskFindingRecord(
                workflow_run_id=workflow_run.id,
                evidence_id=evidence_id,
                title=f.get("title", ""),
                description=f.get("description", ""),
                severity=f.get("severity", "MEDIUM"),
                cfr_refs=f.get("cfr_refs", []),
                citations=f.get("citations", []),
                entities=f.get("entities", [])
            )
            db.add(finding_record)
        
        workflow_run.findings_count = len(findings_data)
        
        # 2. Generate correlation
        correlation = _generate_correlation(evidence, findings_data, db, org_id)
        workflow_run.correlations_count = len(correlation.get("vendor_matches", []))
        
        # 3. Generate action plan
        plan_data = _generate_action_plan(findings_data, None, correlation.get("vendor_matches", []))
        
        # Persist action plan to DB
        action_plan_record = ActionPlanRecord(
            workflow_run_id=workflow_run.id,
            evidence_id=evidence_id,
            rationale=plan_data.get("rationale", ""),
            actions=plan_data.get("top_actions", []),
            owners=plan_data.get("owners", []),
            deadlines=plan_data.get("deadlines", []),
            correlation_data=correlation
        )
        db.add(action_plan_record)
        
        workflow_run.actions_count = len(plan_data.get("top_actions", []))
        
        # Mark workflow as success
        workflow_run.status = WorkflowRunStatus.SUCCESS
        workflow_run.completed_at = datetime.utcnow()
        
        # Create audit log entry
        audit_log = AuditLog(
            organization_id=org_id,
            user_id=user_id,
            action="workflow_run_completed",
            entity_type="workflow_run",
            entity_id=workflow_run.id,
            details={
                "evidence_id": evidence_id,
                "findings_count": workflow_run.findings_count,
                "correlations_count": workflow_run.correlations_count,
                "actions_count": workflow_run.actions_count
            },
            ip_address=request.client.host if request.client else None
        )
        db.add(audit_log)
        
        db.commit()
        
        logger.info(f"Workflow run {workflow_run.id} completed successfully for evidence {evidence_id}")
        
        return WorkflowRunResponse(
            workflow_run_id=workflow_run.id,
            evidence_id=evidence_id,
            status="success",
            findings_count=workflow_run.findings_count,
            correlations_count=workflow_run.correlations_count,
            actions_count=workflow_run.actions_count,
            created_at=workflow_run.created_at.isoformat() if workflow_run.created_at else datetime.utcnow().isoformat(),
            message=f"Workflow completed: {workflow_run.findings_count} findings, {workflow_run.actions_count} actions"
        )
        
    except Exception as e:
        # Mark workflow as failed
        workflow_run.status = WorkflowRunStatus.FAILED
        workflow_run.error_message = str(e)
        workflow_run.completed_at = datetime.utcnow()
        db.commit()
        
        logger.error(f"Workflow run {workflow_run.id} failed: {e}")
        raise HTTPException(status_code=500, detail=f"Workflow failed: {str(e)}")


@router.get("/workflow/runs")
async def list_workflow_runs(
    evidence_id: Optional[int] = Query(None, description="Filter by evidence ID"),
    limit: int = Query(10, le=50),
    user_context: dict = Depends(require_viewer),
    db: Session = Depends(get_db)
):
    """List workflow runs for the organization."""
    query = db.query(WorkflowRun).filter(
        WorkflowRun.organization_id == user_context["org_id"]
    )
    
    if evidence_id:
        query = query.filter(WorkflowRun.evidence_id == evidence_id)
    
    runs = query.order_by(desc(WorkflowRun.created_at)).limit(limit).all()
    
    return [
        {
            "id": run.id,
            "evidence_id": run.evidence_id,
            "status": run.status.value if hasattr(run.status, 'value') else str(run.status),
            "findings_count": run.findings_count or 0,
            "correlations_count": run.correlations_count or 0,
            "actions_count": run.actions_count or 0,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "error_message": run.error_message
        }
        for run in runs
    ]


@router.get("/workflow/runs/{run_id}")
async def get_workflow_run(
    run_id: int,
    user_context: dict = Depends(require_viewer),
    db: Session = Depends(get_db)
):
    """Get details of a specific workflow run including findings and action plan."""
    run = db.query(WorkflowRun).filter(
        WorkflowRun.id == run_id,
        WorkflowRun.organization_id == user_context["org_id"]
    ).first()
    
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    
    # Get findings
    findings = db.query(RiskFindingRecord).filter(
        RiskFindingRecord.workflow_run_id == run_id
    ).all()
    
    # Get action plan
    action_plan = db.query(ActionPlanRecord).filter(
        ActionPlanRecord.workflow_run_id == run_id
    ).first()
    
    return {
        "id": run.id,
        "evidence_id": run.evidence_id,
        "status": run.status.value if hasattr(run.status, 'value') else str(run.status),
        "findings_count": run.findings_count or 0,
        "correlations_count": run.correlations_count or 0,
        "actions_count": run.actions_count or 0,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "error_message": run.error_message,
        "findings": [
            {
                "id": f.id,
                "title": f.title,
                "description": f.description,
                "severity": f.severity,
                "cfr_refs": f.cfr_refs or [],
                "citations": f.citations or [],
                "entities": f.entities or []
            }
            for f in findings
        ],
        "action_plan": {
            "rationale": action_plan.rationale,
            "actions": action_plan.actions or [],
            "owners": action_plan.owners or [],
            "deadlines": action_plan.deadlines or [],
            "correlation_data": action_plan.correlation_data or {}
        } if action_plan else None
    }


@router.get("/export-packet/{evidence_id}")
async def export_audit_packet(
    request: Request,
    evidence_id: int,
    run_id: Optional[int] = Query(None, description="Specific workflow run ID (defaults to latest)"),
    user_context: dict = Depends(require_viewer),
    db: Session = Depends(get_db)
):
    """
    Export a complete audit packet as Markdown file.

    REQUIREMENTS (Golden Workflow Contract):
    - MUST have a successful workflow run (no fallback to cache)
    - MUST contain: workflow_run_id, evidence filenames, risk findings with CFR refs,
      correlation narrative, action plan with owner + deadline
    - Returns 4xx with structured error if requirements not met

    Returns a downloadable Markdown file with Content-Disposition header.
    """
    from fastapi.responses import Response

    org_id = user_context["org_id"]

    # Get evidence
    evidence = db.query(Evidence).filter(
        Evidence.id == evidence_id,
        Evidence.organization_id == org_id
    ).first()

    if not evidence:
        raise HTTPException(status_code=404, detail={
            "error": "evidence_not_found",
            "message": "Evidence not found",
            "evidence_id": evidence_id
        })

    # Validate evidence is processed
    evidence_status = evidence.status.value if hasattr(evidence.status, 'value') else str(evidence.status)
    if evidence_status != "processed":
        raise HTTPException(status_code=400, detail={
            "error": "evidence_not_processed",
            "message": f"Evidence is not processed (status: {evidence_status}). Cannot export audit packet.",
            "evidence_id": evidence_id,
            "status": evidence_status
        })

    # Get workflow run (specific or latest) - REQUIRED, no fallback
    if run_id:
        workflow_run = db.query(WorkflowRun).filter(
            WorkflowRun.id == run_id,
            WorkflowRun.organization_id == org_id,
            WorkflowRun.evidence_id == evidence_id
        ).first()
        if not workflow_run:
            raise HTTPException(status_code=404, detail={
                "error": "workflow_run_not_found",
                "message": f"Workflow run {run_id} not found for evidence {evidence_id}",
                "evidence_id": evidence_id,
                "run_id": run_id
            })
    else:
        workflow_run = db.query(WorkflowRun).filter(
            WorkflowRun.organization_id == org_id,
            WorkflowRun.evidence_id == evidence_id,
            WorkflowRun.status == WorkflowRunStatus.SUCCESS
        ).order_by(desc(WorkflowRun.created_at)).first()

    # STRICT: Workflow run is REQUIRED for export
    if not workflow_run:
        raise HTTPException(status_code=400, detail={
            "error": "no_workflow_run",
            "message": "No successful workflow run found. Run POST /api/risk/workflow/run first.",
            "evidence_id": evidence_id,
            "action_required": "POST /api/risk/workflow/run?evidence_id=" + str(evidence_id)
        })

    # Validate workflow run status
    run_status = workflow_run.status.value if hasattr(workflow_run.status, 'value') else str(workflow_run.status)
    if run_status != "success":
        raise HTTPException(status_code=400, detail={
            "error": "workflow_run_not_successful",
            "message": f"Workflow run {workflow_run.id} has status '{run_status}'. Only successful runs can be exported.",
            "evidence_id": evidence_id,
            "run_id": workflow_run.id,
            "status": run_status,
            "error_message": workflow_run.error_message
        })

    # Get findings from DB - REQUIRED
    db_findings = db.query(RiskFindingRecord).filter(
        RiskFindingRecord.workflow_run_id == workflow_run.id
    ).all()

    if not db_findings:
        raise HTTPException(status_code=500, detail={
            "error": "findings_missing",
            "message": f"Workflow run {workflow_run.id} has no findings. This is a data integrity issue.",
            "evidence_id": evidence_id,
            "run_id": workflow_run.id
        })

    findings = [
        {
            "id": f.id,
            "title": f.title,
            "description": f.description,
            "severity": f.severity,
            "cfr_refs": f.cfr_refs or [],
            "citations": f.citations or []
        }
        for f in db_findings
    ]

    # Validate all findings have CFR refs (Golden Workflow requirement)
    findings_without_cfr = [f for f in findings if not f["cfr_refs"]]
    if findings_without_cfr:
        logger.warning(f"Workflow run {workflow_run.id} has {len(findings_without_cfr)} findings without CFR refs")

    # Get action plan from DB - REQUIRED
    db_action_plan = db.query(ActionPlanRecord).filter(
        ActionPlanRecord.workflow_run_id == workflow_run.id
    ).first()

    if not db_action_plan:
        raise HTTPException(status_code=500, detail={
            "error": "action_plan_missing",
            "message": f"Workflow run {workflow_run.id} has no action plan. This is a data integrity issue.",
            "evidence_id": evidence_id,
            "run_id": workflow_run.id
        })

    action_plan = {
        "rationale": db_action_plan.rationale,
        "top_actions": db_action_plan.actions or []
    }

    # Validate action plan has actions with owners and deadlines
    actions_without_owner = [a for a in action_plan["top_actions"] if not a.get("owner")]
    actions_without_deadline = [a for a in action_plan["top_actions"] if not a.get("deadline")]
    if actions_without_owner or actions_without_deadline:
        logger.warning(f"Workflow run {workflow_run.id} has actions missing owner ({len(actions_without_owner)}) or deadline ({len(actions_without_deadline)})")

    # Get correlation from action plan record - REQUIRED
    correlation = db_action_plan.correlation_data
    if not correlation:
        raise HTTPException(status_code=500, detail={
            "error": "correlation_missing",
            "message": f"Workflow run {workflow_run.id} has no correlation data. This is a data integrity issue.",
            "evidence_id": evidence_id,
            "run_id": workflow_run.id
        })

    # Validate correlation has narrative (watchtower → evidence → risk)
    narrative = correlation.get("narrative", [])
    if not narrative:
        logger.warning(f"Workflow run {workflow_run.id} has empty correlation narrative")

    # Get audit log entries for this evidence and workflow run
    audit_logs = db.query(AuditLog).filter(
        AuditLog.organization_id == org_id,
        AuditLog.entity_type.in_(["evidence", "workflow_run"]),
        AuditLog.entity_id.in_([evidence_id, workflow_run.id])
    ).order_by(AuditLog.timestamp).all()

    # Build Markdown export - workflow_run is guaranteed to exist at this point
    run_status = workflow_run.status.value if hasattr(workflow_run.status, 'value') else str(workflow_run.status)

    md_lines = [
        f"# Audit Packet: {evidence.filename}",
        f"**Workflow Run ID: {workflow_run.id}**",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        "",
        "---",
        "",
        "## Workflow Run Information",
        "",
        f"- **Workflow Run ID**: {workflow_run.id}",
        f"- **Status**: {run_status}",
        f"- **Run Created At**: {workflow_run.created_at.isoformat() if workflow_run.created_at else 'Unknown'}",
        f"- **Run Completed At**: {workflow_run.completed_at.isoformat() if workflow_run.completed_at else 'In Progress'}",
        "",
        "---",
        "",
        "## 1. Evidence Metadata",
        "",
        f"- **ID**: {evidence.id}",
        f"- **Filename**: {evidence.filename}",
        f"- **SHA256**: {evidence.sha256}",
        f"- **Content Type**: {evidence.content_type}",
        f"- **Uploaded At**: {evidence.uploaded_at.isoformat() if evidence.uploaded_at else 'N/A'}",
        f"- **Source**: {evidence.source or 'upload'}",
        "",
    ]
    
    # Add text excerpt
    if evidence.extracted_text:
        excerpt = evidence.extracted_text[:500] + "..." if len(evidence.extracted_text) > 500 else evidence.extracted_text
        md_lines.extend([
            "### Extracted Text Summary",
            "",
            f"```",
            excerpt,
            f"```",
            "",
        ])

    md_lines.extend([
        "---",
        "",
        "## 2. Compliance Findings",
        "",
    ])

    # Findings are guaranteed to exist at this point
    md_lines.append(f"**{len(findings)} finding(s) identified from this workflow run.**\n")
    for i, f in enumerate(findings, 1):
        cfr_refs_str = ', '.join(f.get('cfr_refs', [])) if f.get('cfr_refs') else 'None specified'
        citations_str = ', '.join(f.get('citations', [])) if f.get('citations') else 'None specified'
        md_lines.extend([
            f"### Finding {i}: {f.get('title', 'Untitled')}",
            f"- **Severity**: {f.get('severity', 'UNKNOWN')}",
            f"- **Description**: {f.get('description', '')}",
            f"- **CFR References**: {cfr_refs_str}",
            f"- **Citations**: {citations_str}",
            "",
        ])

    md_lines.extend([
        "---",
        "",
        "## 3. Watchtower Correlation",
        "",
    ])

    # Correlation is guaranteed to exist at this point
    snapshot = correlation.get("watchtower_snapshot", {})
    vendor_matches = correlation.get("vendor_matches", [])
    narrative = correlation.get("narrative", [])

    md_lines.extend([
        "### Supply Chain Intelligence Snapshot",
        "",
        f"- **Total Feed Items**: {snapshot.get('total_feed_items', 0)}",
        f"- **Active Alerts**: {snapshot.get('active_alerts', 0)}",
        f"- **Snapshot Timestamp**: {snapshot.get('timestamp', 'Not recorded')}",
        f"- **Correlation Timestamp**: {correlation.get('correlation_timestamp', 'Not recorded')}",
        "",
    ])

    # Sources status
    sources_status = snapshot.get("sources_status", [])
    if sources_status:
        md_lines.append("### Feed Sources Status\n")
        md_lines.append("| Source | Last Success | Healthy |")
        md_lines.append("|--------|--------------|---------|")
        for s in sources_status:
            healthy = "✓" if s.get("healthy") else "✗"
            md_lines.append(f"| {s.get('source', 'Unknown')} | {s.get('last_success_at', 'Never')} | {healthy} |")
        md_lines.append("")
    else:
        md_lines.append("### Feed Sources Status\n")
        md_lines.append("_No feed sources configured. Consider running POST /api/watchtower/sync._\n")

    # Vendor matches
    md_lines.append("### Vendor Matches\n")
    if vendor_matches:
        md_lines.append("| Vendor | Match Basis | Risk Score | Risk Level |")
        md_lines.append("|--------|-------------|------------|------------|")
        for vm in vendor_matches:
            vendor_id = vm.get("vendor_id") or "Unmatched"
            name = vm.get("name", "Unknown")
            basis = vm.get("match_basis", "Unknown")
            score = vm.get("risk_score") if vm.get("risk_score") is not None else "-"
            level = vm.get("risk_level") or "-"
            md_lines.append(f"| {name} (ID: {vendor_id}) | {basis} | {score} | {level} |")
        md_lines.append("")
    else:
        md_lines.append("_No vendor matches found in document._\n")

    # Narrative - the key correlation output (watchtower → evidence → risk)
    md_lines.append("### Risk Narrative (Watchtower → Evidence → Risk Correlation)\n")
    if narrative:
        for bullet in narrative:
            md_lines.append(f"- {bullet}")
    else:
        md_lines.append("- No significant correlations detected between Watchtower data and evidence.")
    md_lines.append("")

    # Correlated Risks Summary
    high_risk_vendors = [vm for vm in vendor_matches if vm.get("risk_level") in ("high", "critical")]
    md_lines.append("### Correlation Summary\n")
    md_lines.append(f"- **Findings Analyzed**: {len(findings)}")
    md_lines.append(f"- **Vendors Matched**: {len(vendor_matches)}")
    md_lines.append(f"- **High/Critical Risk Vendors**: {len(high_risk_vendors)}")
    md_lines.append(f"- **Active Watchtower Alerts**: {snapshot.get('active_alerts', 0)}")
    md_lines.append("")

    md_lines.extend([
        "---",
        "",
        "## 4. Action Plan",
        "",
    ])

    # Action plan is guaranteed to exist at this point
    md_lines.append(f"**Rationale**: {action_plan.get('rationale', 'No rationale provided')}\n")
    md_lines.append("### Actions:\n")
    actions = action_plan.get("top_actions", [])
    if actions:
        for i, a in enumerate(actions, 1):
            md_lines.extend([
                f"#### {i}. {a.get('title', 'Untitled Action')}",
                f"- **Priority**: {a.get('priority', 'MEDIUM')}",
                f"- **Description**: {a.get('description', 'No description')}",
                f"- **Owner**: {a.get('owner', 'Unassigned')}",
                f"- **Deadline**: {a.get('deadline', 'Not set')}",
                "",
            ])
    else:
        md_lines.append("_No specific actions required based on findings._\n")

    md_lines.extend([
        "---",
        "",
        "## 5. Audit Log",
        "",
        "| Timestamp | Action | Details |",
        "|-----------|--------|---------|",
    ])

    for log in audit_logs:
        details_str = json.dumps(log.details) if log.details else ""
        md_lines.append(f"| {log.timestamp.isoformat() if log.timestamp else 'N/A'} | {log.action} | {details_str} |")

    if not audit_logs:
        md_lines.append("| _No audit entries_ | | |")

    md_lines.extend([
        "",
        "---",
        "",
        "_End of Audit Packet_",
    ])

    markdown_content = "\n".join(md_lines)
    filename = f"audit_packet_run{workflow_run.id}_ev{evidence_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.md"

    # Log the export action
    export_audit_log = AuditLog(
        organization_id=org_id,
        user_id=int(user_context["sub"]),
        action="audit_packet_exported",
        entity_type="workflow_run",
        entity_id=workflow_run.id,
        details={
            "filename": filename,
            "evidence_id": evidence_id,
            "workflow_run_id": workflow_run.id,
            "findings_count": len(findings),
            "actions_count": len(actions),
            "vendor_matches_count": len(vendor_matches),
            "has_correlation": True,
            "has_action_plan": True
        },
        ip_address=request.client.host if request.client else None
    )
    db.add(export_audit_log)
    db.commit()

    logger.info(f"Exported audit packet for evidence {evidence_id}, workflow run {workflow_run.id}")

    # Return as downloadable file
    return Response(
        content=markdown_content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.get("/health")
async def risk_health(
    user_context: dict = Depends(require_viewer),
    db: Session = Depends(get_db)
):
    """
    Health check for risk findings module.
    Requires authentication - returns 200 when authenticated.
    """
    # Count workflow runs
    total_runs = db.query(WorkflowRun).filter(
        WorkflowRun.organization_id == user_context["org_id"]
    ).count()

    success_runs = db.query(WorkflowRun).filter(
        WorkflowRun.organization_id == user_context["org_id"],
        WorkflowRun.status == WorkflowRunStatus.SUCCESS
    ).count()

    return {
        "status": "healthy",
        "module": "risk_findings",
        "total_workflow_runs": total_runs,
        "successful_runs": success_runs,
        "cache_findings": len(_findings_cache),
        "cache_correlations": len(_correlations_cache)
    }


# ============= GOLDEN WORKFLOW HEALTH CHECK (PUBLIC) =============

@router.get("/health/golden-workflow")
async def golden_workflow_health(
    db: Session = Depends(get_db)
):
    """
    Golden Workflow readiness check.

    NO AUTHENTICATION REQUIRED - this is a public health endpoint.

    Returns:
    - ready: true if the Golden Workflow can execute end-to-end
    - blocking_reason: null if ready, otherwise explains what's blocking

    Checks:
    1. Database connectivity
    2. Required tables exist (Evidence, WorkflowRun, etc.)
    3. At least one processed evidence exists (for demo/testing)
    """
    blocking_reasons = []

    try:
        # Check 1: Database connectivity
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
    except Exception as e:
        return {
            "ready": False,
            "blocking_reason": f"Database connection failed: {str(e)}"
        }

    try:
        # Check 2: Required tables exist and are queryable
        evidence_count = db.query(Evidence).count()
        workflow_count = db.query(WorkflowRun).count()

        # Check 3: At least one processed evidence exists
        processed_evidence_count = db.query(Evidence).filter(
            Evidence.status == EvidenceStatus.PROCESSED
        ).count()

        if processed_evidence_count == 0:
            blocking_reasons.append(
                "No processed evidence available. Upload evidence via POST /api/evidence first."
            )

        # Check 4: Check for any stuck/failed evidence that might indicate issues
        failed_evidence_count = db.query(Evidence).filter(
            Evidence.status == EvidenceStatus.FAILED
        ).count()

        pending_evidence_count = db.query(Evidence).filter(
            Evidence.status == EvidenceStatus.PENDING
        ).count()

        processing_evidence_count = db.query(Evidence).filter(
            Evidence.status == EvidenceStatus.PROCESSING
        ).count()

        # Informational: not blocking, but good to know
        successful_runs = db.query(WorkflowRun).filter(
            WorkflowRun.status == WorkflowRunStatus.SUCCESS
        ).count()

        failed_runs = db.query(WorkflowRun).filter(
            WorkflowRun.status == WorkflowRunStatus.FAILED
        ).count()

    except Exception as e:
        return {
            "ready": False,
            "blocking_reason": f"Database query failed: {str(e)}"
        }

    is_ready = len(blocking_reasons) == 0

    return {
        "ready": is_ready,
        "blocking_reason": blocking_reasons[0] if blocking_reasons else None,
        "details": {
            "evidence": {
                "total": evidence_count,
                "processed": processed_evidence_count,
                "pending": pending_evidence_count,
                "processing": processing_evidence_count,
                "failed": failed_evidence_count
            },
            "workflow_runs": {
                "total": workflow_count,
                "successful": successful_runs,
                "failed": failed_runs
            }
        }
    }

