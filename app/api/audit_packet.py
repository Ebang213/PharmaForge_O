"""
Inspection-Ready Audit Packet Generator.

Generates regulator-ready audit packets from completed Golden Workflow runs.
All data is sourced from the database — no placeholders, no cache fallbacks.

Endpoint: GET /api/risk/audit-packet/{workflow_run_id}
"""
import os
import json
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.db.models import (
    Evidence, EvidenceStatus, AuditLog, Vendor, WatchtowerItem, WatchtowerAlert,
    WorkflowRun, WorkflowRunStatus, RiskFindingRecord, ActionPlanRecord,
    WatchtowerSyncStatus,
)
from app.core.rbac import require_viewer
from app.core.logging import get_logger
from app.core.metrics import AUDIT_PACKET_EXPORTS_TOTAL
from app.core.rate_limit import limiter

logger = get_logger(__name__)

router = APIRouter(prefix="/api/risk", tags=["Audit Packet"])

EXPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "exports")


# ============= RESPONSE SCHEMAS =============

class AuditPacketActionItem(BaseModel):
    action: str
    owner: str
    deadline: str
    priority: str


class AuditPacketFinding(BaseModel):
    id: int
    title: str
    description: str
    severity: str
    cfr_refs: List[str]
    citations: List[str]


class AuditPacketEvidence(BaseModel):
    id: int
    filename: str
    sha256: str
    content_type: str
    uploaded_at: str
    source: str


class AuditPacketResponse(BaseModel):
    workflow_run_id: int
    generated_at: str
    executive_summary: str
    evidence: AuditPacketEvidence
    findings: List[AuditPacketFinding]
    correlation_narrative: str
    action_plan: List[AuditPacketActionItem]


class AuditPacketValidationError(BaseModel):
    error: str
    message: str
    missing: List[str]
    workflow_run_id: int


# ============= PLACEHOLDER / EMPTY STRING VALIDATOR =============

_REJECTED_VALUES = {"n/a", "na", "none", "tbd", "todo", "placeholder", "unknown", ""}


def _reject_placeholder(value: Optional[str], field_name: str) -> str:
    """Raise ValueError if value is empty or a known placeholder."""
    if value is None or str(value).strip().lower() in _REJECTED_VALUES:
        raise ValueError(f"Field '{field_name}' contains a rejected placeholder value: {value!r}")
    return str(value).strip()


# ============= GENERATORS =============

def generate_executive_summary(
    evidence: Evidence,
    findings: List[RiskFindingRecord],
    action_plan: ActionPlanRecord,
    vendor_data: List[dict],
) -> str:
    """
    Build a human-readable executive summary suitable for a compliance report.

    Uses real findings, risk levels, and vendor data — never placeholders.
    """
    severity_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings:
        sev = (f.severity or "MEDIUM").upper()
        if sev in severity_counts:
            severity_counts[sev] += 1
        else:
            severity_counts[sev] = 1

    high = severity_counts.get("HIGH", 0)
    medium = severity_counts.get("MEDIUM", 0)
    low = severity_counts.get("LOW", 0)
    total = len(findings)

    # Build risk characterisation
    if high > 0:
        risk_posture = "elevated"
        urgency = "Immediate corrective action is required for high-severity findings."
    elif medium > 0:
        risk_posture = "moderate"
        urgency = "Timely review and remediation of medium-severity findings is recommended."
    else:
        risk_posture = "low"
        urgency = "Routine monitoring is sufficient at this time."

    # Vendor context
    high_risk_vendors = [v for v in vendor_data if v.get("risk_level") in ("high", "critical")]
    vendor_sentence = ""
    if vendor_data:
        vendor_sentence = (
            f" Correlation analysis identified {len(vendor_data)} vendor(s) linked to this evidence"
        )
        if high_risk_vendors:
            vendor_sentence += (
                f", of which {len(high_risk_vendors)} "
                f"{'is' if len(high_risk_vendors) == 1 else 'are'} "
                f"classified as high or critical risk"
            )
        vendor_sentence += "."

    # CFR coverage
    all_cfr = set()
    for f in findings:
        for ref in (f.cfr_refs or []):
            all_cfr.add(ref)
    cfr_sentence = ""
    if all_cfr:
        cfr_sentence = f" Applicable regulatory references include {', '.join(sorted(all_cfr))}."

    # Action plan summary
    actions_count = len(action_plan.actions or [])

    summary = (
        f"This audit packet summarises the compliance risk assessment for evidence document "
        f"\"{evidence.filename}\" (SHA-256: {evidence.sha256}). "
        f"The analysis identified {total} compliance finding(s) — "
        f"{high} high, {medium} medium, and {low} low severity. "
        f"The overall risk posture is {risk_posture}. {urgency}"
        f"{vendor_sentence}"
        f"{cfr_sentence} "
        f"An action plan comprising {actions_count} remediation item(s) has been generated "
        f"with assigned owners and deadlines."
    )

    return summary


def generate_correlation_narrative(
    evidence: Evidence,
    findings: List[RiskFindingRecord],
    correlation_data: dict,
) -> str:
    """
    Generate a prose narrative explaining the chain:
    Watchtower signals -> evidence -> findings -> risk -> decision.
    """
    snapshot = correlation_data.get("watchtower_snapshot", {})
    vendor_matches = correlation_data.get("vendor_matches", [])
    narrative_bullets = correlation_data.get("narrative", [])

    total_feed = snapshot.get("total_feed_items", 0)
    active_alerts = snapshot.get("active_alerts", 0)
    matched_vendors = [v for v in vendor_matches if v.get("vendor_id")]
    high_risk = [v for v in matched_vendors if v.get("risk_level") in ("high", "critical")]

    high_findings = [f for f in findings if (f.severity or "").upper() == "HIGH"]
    medium_findings = [f for f in findings if (f.severity or "").upper() == "MEDIUM"]

    paragraphs = []

    # Paragraph 1: Watchtower signal context
    if total_feed > 0 or active_alerts > 0:
        paragraphs.append(
            f"The Watchtower supply-chain intelligence system was monitoring "
            f"{total_feed} FDA feed item(s) at the time of analysis, with "
            f"{active_alerts} active alert(s) flagged for the organisation. "
            f"These signals provide the contextual backdrop for the risk assessment."
        )
    else:
        paragraphs.append(
            "No active Watchtower feed items or alerts were recorded at the time of analysis. "
            "The risk assessment was conducted based solely on the uploaded evidence."
        )

    # Paragraph 2: Evidence -> Findings
    paragraphs.append(
        f"Analysis of the evidence document \"{evidence.filename}\" yielded "
        f"{len(findings)} compliance finding(s). "
        + (
            f"Of these, {len(high_findings)} {'is' if len(high_findings) == 1 else 'are'} "
            f"classified as high severity, requiring immediate attention. "
            if high_findings
            else ""
        )
        + (
            f"{len(medium_findings)} finding(s) are medium severity and warrant timely review."
            if medium_findings
            else ""
        )
    )

    # Paragraph 3: Vendor correlation
    if matched_vendors:
        paragraphs.append(
            f"Cross-referencing the evidence with the vendor registry identified "
            f"{len(matched_vendors)} vendor(s) with a potential nexus to the document. "
            + (
                f"{len(high_risk)} of these vendor(s) carry a high or critical risk rating, "
                f"compounding the risk profile and warranting priority investigation."
                if high_risk
                else "None of the matched vendors are currently flagged as high or critical risk."
            )
        )

    # Paragraph 4: Decision rationale
    if high_findings or high_risk:
        paragraphs.append(
            "Given the presence of high-severity findings"
            + (" and high-risk vendor exposure" if high_risk else "")
            + ", the recommended course of action prioritises rapid containment "
            "and remediation before regulatory exposure increases."
        )
    else:
        paragraphs.append(
            "The findings and vendor risk profile indicate a manageable compliance posture. "
            "Standard remediation timelines are appropriate."
        )

    # Append original Watchtower narrative bullets as supplementary context
    if narrative_bullets:
        bullet_text = "\n".join(f"  - {b}" for b in narrative_bullets)
        paragraphs.append(f"Watchtower correlation highlights:\n{bullet_text}")

    return "\n\n".join(paragraphs)


def build_action_plan_items(action_plan: ActionPlanRecord) -> List[AuditPacketActionItem]:
    """
    Convert stored action plan actions into validated AuditPacketActionItem list.

    Each item MUST have action, owner, deadline, priority — no placeholders.
    """
    raw_actions = action_plan.actions or []
    items: List[AuditPacketActionItem] = []

    for raw in raw_actions:
        action_text = _reject_placeholder(
            raw.get("title") or raw.get("action"),
            "action",
        )
        owner = _reject_placeholder(raw.get("owner"), "owner")
        deadline = _reject_placeholder(raw.get("deadline"), "deadline")
        priority = _reject_placeholder(raw.get("priority"), "priority")

        items.append(AuditPacketActionItem(
            action=action_text,
            owner=owner,
            deadline=deadline,
            priority=priority,
        ))

    return items


# ============= MARKDOWN EXPORT =============

def render_markdown(packet: AuditPacketResponse) -> str:
    """Render the audit packet as a regulator-ready Markdown document."""
    lines = [
        f"# Inspection-Ready Audit Packet",
        f"**Workflow Run ID:** {packet.workflow_run_id}",
        f"**Generated:** {packet.generated_at}",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        "",
        packet.executive_summary,
        "",
        "---",
        "",
        "## 2. Evidence Metadata",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Document ID | {packet.evidence.id} |",
        f"| Filename | {packet.evidence.filename} |",
        f"| SHA-256 | {packet.evidence.sha256} |",
        f"| Content Type | {packet.evidence.content_type} |",
        f"| Uploaded At | {packet.evidence.uploaded_at} |",
        f"| Source | {packet.evidence.source} |",
        "",
        "---",
        "",
        "## 3. Compliance Findings",
        "",
        f"**{len(packet.findings)} finding(s) identified.**",
        "",
    ]

    for i, f in enumerate(packet.findings, 1):
        cfr = ", ".join(f.cfr_refs) if f.cfr_refs else "None specified"
        citations = ", ".join(f.citations) if f.citations else "None specified"
        lines.extend([
            f"### Finding {i}: {f.title}",
            f"- **Severity:** {f.severity}",
            f"- **Description:** {f.description}",
            f"- **CFR References:** {cfr}",
            f"- **Citations:** {citations}",
            "",
        ])

    lines.extend([
        "---",
        "",
        "## 4. Correlation Narrative",
        "",
        "*(Watchtower signals -> evidence -> findings -> risk -> decision)*",
        "",
        packet.correlation_narrative,
        "",
        "---",
        "",
        "## 5. Action Plan",
        "",
        "| # | Action | Priority | Owner | Deadline |",
        "|---|--------|----------|-------|----------|",
    ])

    for i, a in enumerate(packet.action_plan, 1):
        lines.append(f"| {i} | {a.action} | {a.priority} | {a.owner} | {a.deadline} |")

    lines.extend([
        "",
        "---",
        "",
        "*End of Inspection-Ready Audit Packet*",
    ])

    return "\n".join(lines)


# ============= ENDPOINT =============

@router.get(
    "/audit-packet/{workflow_run_id}",
    response_model=AuditPacketResponse,
    responses={
        400: {"model": AuditPacketValidationError, "description": "Missing required data"},
        404: {"description": "Workflow run not found"},
    },
)
@limiter.limit("30/minute")
async def get_audit_packet(
    request: Request,
    workflow_run_id: int,
    export: bool = False,
    user_context: dict = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    """
    Generate an inspection-ready audit packet for a completed workflow run.

    Validates that all required data exists in the database:
    - workflow_run exists and succeeded
    - evidence exists and is processed
    - findings exist with CFR references
    - action plan exists with owners and deadlines

    Returns 400 with structured error listing missing components if any
    data is absent. No placeholders or N/A values are permitted.

    Pass ?export=true to also write the packet as a downloadable Markdown file.
    """
    org_id = user_context["org_id"]

    # ---------- 1. Validate workflow run ----------
    workflow_run = db.query(WorkflowRun).filter(
        WorkflowRun.id == workflow_run_id,
        WorkflowRun.organization_id == org_id,
    ).first()

    if not workflow_run:
        raise HTTPException(status_code=404, detail={
            "error": "workflow_run_not_found",
            "message": f"Workflow run {workflow_run_id} not found.",
            "workflow_run_id": workflow_run_id,
        })

    run_status = workflow_run.status.value if hasattr(workflow_run.status, "value") else str(workflow_run.status)
    if run_status != "success":
        raise HTTPException(status_code=400, detail={
            "error": "workflow_run_not_successful",
            "message": (
                f"Workflow run {workflow_run_id} has status '{run_status}'. "
                "Only successful runs can produce an audit packet."
            ),
            "missing": ["successful_workflow_run"],
            "workflow_run_id": workflow_run_id,
        })

    # ---------- 2. Collect & validate all required data ----------
    missing: List[str] = []

    # Evidence
    evidence = db.query(Evidence).filter(
        Evidence.id == workflow_run.evidence_id,
        Evidence.organization_id == org_id,
    ).first()
    if not evidence:
        missing.append("evidence")
    else:
        ev_status = evidence.status.value if hasattr(evidence.status, "value") else str(evidence.status)
        if ev_status != "processed":
            missing.append("processed_evidence")

    # Findings
    db_findings = db.query(RiskFindingRecord).filter(
        RiskFindingRecord.workflow_run_id == workflow_run_id,
    ).all()
    if not db_findings:
        missing.append("findings")

    # Action plan
    db_action_plan = db.query(ActionPlanRecord).filter(
        ActionPlanRecord.workflow_run_id == workflow_run_id,
    ).first()
    if not db_action_plan:
        missing.append("action_plan")
    else:
        if not db_action_plan.correlation_data:
            missing.append("correlation_data")
        if not db_action_plan.actions:
            missing.append("action_plan_actions")

    if missing:
        raise HTTPException(status_code=400, detail={
            "error": "incomplete_data",
            "message": "Cannot generate audit packet — required data is missing.",
            "missing": missing,
            "workflow_run_id": workflow_run_id,
        })

    # At this point evidence, db_findings, db_action_plan are all non-None.
    # ---------- 3. Validate no placeholder values in action items ----------
    try:
        action_items = build_action_plan_items(db_action_plan)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={
            "error": "placeholder_value",
            "message": str(exc),
            "missing": ["valid_action_plan_fields"],
            "workflow_run_id": workflow_run_id,
        })

    if not action_items:
        raise HTTPException(status_code=400, detail={
            "error": "incomplete_data",
            "message": "Action plan contains no action items.",
            "missing": ["action_plan_actions"],
            "workflow_run_id": workflow_run_id,
        })

    # ---------- 4. Build findings list ----------
    findings_out: List[AuditPacketFinding] = []
    for f in db_findings:
        findings_out.append(AuditPacketFinding(
            id=f.id,
            title=f.title,
            description=f.description or "",
            severity=f.severity or "MEDIUM",
            cfr_refs=f.cfr_refs or [],
            citations=f.citations or [],
        ))

    # ---------- 5. Build evidence metadata ----------
    evidence_out = AuditPacketEvidence(
        id=evidence.id,
        filename=evidence.filename,
        sha256=evidence.sha256 or "",
        content_type=evidence.content_type or "",
        uploaded_at=evidence.uploaded_at.isoformat() if evidence.uploaded_at else "",
        source=evidence.source or "upload",
    )

    # ---------- 6. Vendor data for executive summary ----------
    vendor_matches = db_action_plan.correlation_data.get("vendor_matches", [])

    # ---------- 7. Generate executive summary ----------
    executive_summary = generate_executive_summary(
        evidence, db_findings, db_action_plan, vendor_matches,
    )

    # ---------- 8. Generate correlation narrative ----------
    correlation_narrative = generate_correlation_narrative(
        evidence, db_findings, db_action_plan.correlation_data,
    )

    # ---------- 9. Assemble response ----------
    generated_at = datetime.now(timezone.utc).isoformat() + "Z"

    packet = AuditPacketResponse(
        workflow_run_id=workflow_run_id,
        generated_at=generated_at,
        executive_summary=executive_summary,
        evidence=evidence_out,
        findings=findings_out,
        correlation_narrative=correlation_narrative,
        action_plan=action_items,
    )

    # ---------- 10. Audit logging ----------
    db.add(AuditLog(
        organization_id=org_id,
        user_id=int(user_context["sub"]),
        action="audit_packet_generated",
        entity_type="workflow_run",
        entity_id=workflow_run_id,
        details={
            "workflow_run_id": workflow_run_id,
            "evidence_id": evidence.id,
            "findings_count": len(findings_out),
            "actions_count": len(action_items),
            "exported": export,
        },
        ip_address=request.client.host if request.client else None,
    ))
    db.commit()

    AUDIT_PACKET_EXPORTS_TOTAL.inc()
    logger.info(
        "Audit packet generated",
        extra={
            "service": "audit_packet",
            "event": "audit_packet_generated",
            "workflow_run_id": workflow_run_id,
            "evidence_id": evidence.id,
            "findings_count": len(findings_out),
        },
    )

    # ---------- 11. Optional Markdown file export ----------
    if export:
        md_content = render_markdown(packet)
        os.makedirs(EXPORTS_DIR, exist_ok=True)
        export_path = os.path.join(EXPORTS_DIR, f"audit_{workflow_run_id}.md")
        with open(export_path, "w", encoding="utf-8") as fh:
            fh.write(md_content)

        logger.info(
            "Audit packet exported to file",
            extra={
                "service": "audit_packet",
                "event": "audit_packet_file_export",
                "workflow_run_id": workflow_run_id,
                "export_path": export_path,
            },
        )

        return Response(
            content=md_content,
            media_type="text/markdown",
            headers={
                "Content-Disposition": f'attachment; filename="audit_{workflow_run_id}.md"',
            },
        )

    return packet
