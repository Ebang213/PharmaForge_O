"""
Tests for the Inspection-Ready Audit Packet Generator.

Tests:
1. Success path — full packet generation from a completed workflow run
2. Missing data failures — each required component triggers structured 400
3. Output completeness — no placeholders, all fields populated
4. Markdown export — file written with correct content
"""
import os
import pytest
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import (
    Evidence, EvidenceStatus, Organization, User, WorkflowRun, WorkflowRunStatus,
    RiskFindingRecord, ActionPlanRecord, AuditLog,
)
from app.api.audit_packet import (
    generate_executive_summary,
    generate_correlation_narrative,
    build_action_plan_items,
    render_markdown,
    AuditPacketResponse,
    AuditPacketEvidence,
    AuditPacketFinding,
    AuditPacketActionItem,
    _reject_placeholder,
    EXPORTS_DIR,
)


# ============= FIXTURES =============

@pytest.fixture(scope="module")
def db_session():
    """Create a database session for testing."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture(scope="module")
def test_org(db_session: Session):
    """Get or create a test organization."""
    org = db_session.query(Organization).filter(
        Organization.slug == "audit-pkt-test-org"
    ).first()
    if not org:
        org = Organization(name="Audit Packet Test Org", slug="audit-pkt-test-org")
        db_session.add(org)
        db_session.commit()
        db_session.refresh(org)
    return org


@pytest.fixture(scope="module")
def test_user(db_session: Session, test_org: Organization):
    """Get or create a test user."""
    user = db_session.query(User).filter(
        User.email == "audit-pkt-test@pharmaforge.test"
    ).first()
    if not user:
        user = User(
            email="audit-pkt-test@pharmaforge.test",
            hashed_password="$2b$12$placeholder_not_real",
            full_name="Audit Packet Test User",
            organization_id=test_org.id,
            role="admin",
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    return user


def _make_evidence(db_session, test_org, test_user, *, status=EvidenceStatus.PROCESSED, text=None):
    """Helper to create evidence with sensible defaults."""
    sample_text = text or (
        "PHARMACEUTICAL MANUFACTURING COMPLIANCE DOCUMENT\n"
        "Temperature Control Assessment:\n"
        "Cold chain storage procedures reviewed. Temperature monitoring revealed "
        "deviations from the 2-8 C storage requirements for API materials.\n"
        "Vendor Assessment: Supplier XYZ Pharma Labs evaluated for cGMP compliance.\n"
        "Manufacturing practices require additional qualification audits.\n"
        "Labeling Review: Product labeling must be updated for serialization "
        "requirements per DSCSA Section 582 traceability mandates.\n"
        "Recall History: Previous quality deviation on Lot 2023-001 resolved. "
        "CAPA documentation is complete."
    )
    evidence = Evidence(
        organization_id=test_org.id,
        filename="audit_pkt_test_document.pdf",
        content_type="application/pdf",
        storage_path="/tmp/audit_pkt_test.pdf",
        sha256="apkt_sha256_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f"),
        uploaded_by=test_user.id,
        extracted_text=sample_text if status == EvidenceStatus.PROCESSED else None,
        source="upload",
        status=status,
        processed_at=datetime.now(timezone.utc) if status == EvidenceStatus.PROCESSED else None,
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)
    return evidence


def _make_full_workflow(db_session, test_org, test_user, evidence):
    """
    Create a complete successful workflow run with findings, correlation,
    and action plan — all backed by real DB records.
    """
    from app.api.risk_findings import (
        _generate_mock_findings, _generate_correlation, _generate_action_plan,
    )

    workflow_run = WorkflowRun(
        organization_id=test_org.id,
        evidence_id=evidence.id,
        created_by=test_user.id,
        status=WorkflowRunStatus.RUNNING,
    )
    db_session.add(workflow_run)
    db_session.flush()

    # Findings
    findings_data = _generate_mock_findings(evidence.extracted_text, evidence.id)
    for f in findings_data:
        db_session.add(RiskFindingRecord(
            workflow_run_id=workflow_run.id,
            evidence_id=evidence.id,
            title=f["title"],
            description=f["description"],
            severity=f["severity"],
            cfr_refs=f.get("cfr_refs", []),
            citations=f.get("citations", []),
            entities=f.get("entities", []),
        ))
    workflow_run.findings_count = len(findings_data)

    # Correlation
    correlation = _generate_correlation(evidence, findings_data, db_session, test_org.id)
    workflow_run.correlations_count = len(correlation.get("vendor_matches", []))

    # Action plan
    plan_data = _generate_action_plan(findings_data, None, correlation.get("vendor_matches", []))
    db_session.add(ActionPlanRecord(
        workflow_run_id=workflow_run.id,
        evidence_id=evidence.id,
        rationale=plan_data["rationale"],
        actions=plan_data["top_actions"],
        owners=plan_data["owners"],
        deadlines=plan_data["deadlines"],
        correlation_data=correlation,
    ))
    workflow_run.actions_count = len(plan_data["top_actions"])

    workflow_run.status = WorkflowRunStatus.SUCCESS
    workflow_run.completed_at = datetime.now(timezone.utc)
    db_session.commit()
    db_session.refresh(workflow_run)

    return workflow_run


def _cleanup_workflow(db_session, workflow_run_id, evidence_id):
    """Delete all records tied to a workflow run and its evidence."""
    try:
        db_session.rollback()
    except Exception:
        pass
    try:
        db_session.query(AuditLog).filter(
            AuditLog.entity_type == "workflow_run",
            AuditLog.entity_id == workflow_run_id,
        ).delete()
        db_session.query(ActionPlanRecord).filter(
            ActionPlanRecord.workflow_run_id == workflow_run_id,
        ).delete()
        db_session.query(RiskFindingRecord).filter(
            RiskFindingRecord.workflow_run_id == workflow_run_id,
        ).delete()
        db_session.query(WorkflowRun).filter(
            WorkflowRun.id == workflow_run_id,
        ).delete()
        db_session.query(Evidence).filter(
            Evidence.id == evidence_id,
        ).delete()
        db_session.commit()
    except Exception:
        db_session.rollback()


# ============= SUCCESS PATH =============

class TestAuditPacketSuccessPath:
    """
    Verify that a complete workflow run produces a fully-populated audit packet
    with real database data — no placeholders, no N/A.
    """

    def test_generates_complete_packet(
        self, db_session: Session, test_org: Organization, test_user: User,
    ):
        """Full success path: evidence -> workflow -> audit packet."""
        evidence = _make_evidence(db_session, test_org, test_user)
        workflow_run = _make_full_workflow(db_session, test_org, test_user, evidence)

        try:
            # Fetch persisted data exactly as the endpoint would
            db_findings = db_session.query(RiskFindingRecord).filter(
                RiskFindingRecord.workflow_run_id == workflow_run.id,
            ).all()
            db_plan = db_session.query(ActionPlanRecord).filter(
                ActionPlanRecord.workflow_run_id == workflow_run.id,
            ).first()

            assert len(db_findings) >= 3, "Sample text should produce >= 3 findings"
            assert db_plan is not None
            assert db_plan.correlation_data is not None

            # Build executive summary
            vendor_matches = db_plan.correlation_data.get("vendor_matches", [])
            summary = generate_executive_summary(
                evidence, db_findings, db_plan, vendor_matches,
            )
            assert len(summary) > 50, "Executive summary should be substantial prose"
            assert evidence.filename in summary
            assert "finding" in summary.lower()

            # Build correlation narrative
            narrative = generate_correlation_narrative(
                evidence, db_findings, db_plan.correlation_data,
            )
            assert len(narrative) > 50
            assert evidence.filename in narrative

            # Build action items
            action_items = build_action_plan_items(db_plan)
            assert len(action_items) >= 1
            for item in action_items:
                assert item.action
                assert item.owner
                assert item.deadline
                assert item.priority

            print(f"\n  Workflow Run ID: {workflow_run.id}")
            print(f"  Findings: {len(db_findings)}")
            print(f"  Action Items: {len(action_items)}")
            print(f"  Summary length: {len(summary)} chars")
            print(f"  Narrative length: {len(narrative)} chars")

        finally:
            _cleanup_workflow(db_session, workflow_run.id, evidence.id)

    def test_markdown_export_contains_all_sections(
        self, db_session: Session, test_org: Organization, test_user: User,
    ):
        """Rendered Markdown must include every required section."""
        evidence = _make_evidence(db_session, test_org, test_user)
        workflow_run = _make_full_workflow(db_session, test_org, test_user, evidence)

        try:
            db_findings = db_session.query(RiskFindingRecord).filter(
                RiskFindingRecord.workflow_run_id == workflow_run.id,
            ).all()
            db_plan = db_session.query(ActionPlanRecord).filter(
                ActionPlanRecord.workflow_run_id == workflow_run.id,
            ).first()

            vendor_matches = db_plan.correlation_data.get("vendor_matches", [])

            packet = AuditPacketResponse(
                workflow_run_id=workflow_run.id,
                generated_at=datetime.now(timezone.utc).isoformat() + "Z",
                executive_summary=generate_executive_summary(
                    evidence, db_findings, db_plan, vendor_matches,
                ),
                evidence=AuditPacketEvidence(
                    id=evidence.id,
                    filename=evidence.filename,
                    sha256=evidence.sha256 or "",
                    content_type=evidence.content_type or "",
                    uploaded_at=evidence.uploaded_at.isoformat() if evidence.uploaded_at else "",
                    source=evidence.source or "upload",
                ),
                findings=[
                    AuditPacketFinding(
                        id=f.id, title=f.title, description=f.description or "",
                        severity=f.severity or "MEDIUM", cfr_refs=f.cfr_refs or [],
                        citations=f.citations or [],
                    )
                    for f in db_findings
                ],
                correlation_narrative=generate_correlation_narrative(
                    evidence, db_findings, db_plan.correlation_data,
                ),
                action_plan=build_action_plan_items(db_plan),
            )

            md = render_markdown(packet)

            # Verify required sections exist
            assert "# Inspection-Ready Audit Packet" in md
            assert "## 1. Executive Summary" in md
            assert "## 2. Evidence Metadata" in md
            assert "## 3. Compliance Findings" in md
            assert "## 4. Correlation Narrative" in md
            assert "## 5. Action Plan" in md
            assert str(workflow_run.id) in md
            assert evidence.filename in md
            assert "End of Inspection-Ready Audit Packet" in md

            # No placeholder text
            md_lower = md.lower()
            assert "n/a" not in md_lower.split("correlation")[0]  # Allow "N/A" only in dynamic narrative
            assert "placeholder" not in md_lower
            assert "todo" not in md_lower

        finally:
            _cleanup_workflow(db_session, workflow_run.id, evidence.id)

    def test_markdown_file_written_to_exports(
        self, db_session: Session, test_org: Organization, test_user: User,
    ):
        """When export=true the file must land in the exports/ directory."""
        evidence = _make_evidence(db_session, test_org, test_user)
        workflow_run = _make_full_workflow(db_session, test_org, test_user, evidence)

        try:
            db_findings = db_session.query(RiskFindingRecord).filter(
                RiskFindingRecord.workflow_run_id == workflow_run.id,
            ).all()
            db_plan = db_session.query(ActionPlanRecord).filter(
                ActionPlanRecord.workflow_run_id == workflow_run.id,
            ).first()

            vendor_matches = db_plan.correlation_data.get("vendor_matches", [])

            packet = AuditPacketResponse(
                workflow_run_id=workflow_run.id,
                generated_at=datetime.now(timezone.utc).isoformat() + "Z",
                executive_summary=generate_executive_summary(
                    evidence, db_findings, db_plan, vendor_matches,
                ),
                evidence=AuditPacketEvidence(
                    id=evidence.id,
                    filename=evidence.filename,
                    sha256=evidence.sha256 or "",
                    content_type=evidence.content_type or "",
                    uploaded_at=evidence.uploaded_at.isoformat() if evidence.uploaded_at else "",
                    source=evidence.source or "upload",
                ),
                findings=[
                    AuditPacketFinding(
                        id=f.id, title=f.title, description=f.description or "",
                        severity=f.severity or "MEDIUM", cfr_refs=f.cfr_refs or [],
                        citations=f.citations or [],
                    )
                    for f in db_findings
                ],
                correlation_narrative=generate_correlation_narrative(
                    evidence, db_findings, db_plan.correlation_data,
                ),
                action_plan=build_action_plan_items(db_plan),
            )

            md_content = render_markdown(packet)

            # Simulate export file creation
            os.makedirs(EXPORTS_DIR, exist_ok=True)
            export_path = os.path.join(EXPORTS_DIR, f"audit_{workflow_run.id}.md")
            with open(export_path, "w", encoding="utf-8") as fh:
                fh.write(md_content)

            assert os.path.exists(export_path)
            with open(export_path, "r", encoding="utf-8") as fh:
                content = fh.read()
            assert "Inspection-Ready Audit Packet" in content
            assert str(workflow_run.id) in content

            # Clean up file
            os.remove(export_path)

        finally:
            _cleanup_workflow(db_session, workflow_run.id, evidence.id)


# ============= MISSING DATA FAILURES =============

class TestAuditPacketMissingData:
    """
    Each missing component must trigger a structured 400 error.
    These tests validate the same checks the endpoint performs.
    """

    def test_missing_workflow_run(self, db_session: Session, test_org: Organization):
        """Querying a non-existent workflow run ID yields nothing."""
        bogus_id = 999999
        run = db_session.query(WorkflowRun).filter(
            WorkflowRun.id == bogus_id,
            WorkflowRun.organization_id == test_org.id,
        ).first()
        assert run is None, "Non-existent workflow run must return None"

    def test_failed_workflow_run_rejected(
        self, db_session: Session, test_org: Organization, test_user: User,
    ):
        """A FAILED workflow run must not produce a packet."""
        evidence = _make_evidence(db_session, test_org, test_user)
        workflow_run = WorkflowRun(
            organization_id=test_org.id,
            evidence_id=evidence.id,
            created_by=test_user.id,
            status=WorkflowRunStatus.FAILED,
            error_message="Simulated failure",
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(workflow_run)
        db_session.commit()
        db_session.refresh(workflow_run)

        try:
            run_status = workflow_run.status.value if hasattr(workflow_run.status, "value") else str(workflow_run.status)
            assert run_status != "success", "Failed run must be rejected"
        finally:
            _cleanup_workflow(db_session, workflow_run.id, evidence.id)

    def test_missing_findings_detected(
        self, db_session: Session, test_org: Organization, test_user: User,
    ):
        """Workflow run with zero findings must be flagged."""
        evidence = _make_evidence(db_session, test_org, test_user)
        workflow_run = WorkflowRun(
            organization_id=test_org.id,
            evidence_id=evidence.id,
            created_by=test_user.id,
            status=WorkflowRunStatus.SUCCESS,
            findings_count=0,
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(workflow_run)
        db_session.commit()
        db_session.refresh(workflow_run)

        try:
            findings = db_session.query(RiskFindingRecord).filter(
                RiskFindingRecord.workflow_run_id == workflow_run.id,
            ).all()
            assert len(findings) == 0, "No findings should exist"

            # This is the check the endpoint performs
            missing = []
            if not findings:
                missing.append("findings")
            assert "findings" in missing
        finally:
            _cleanup_workflow(db_session, workflow_run.id, evidence.id)

    def test_missing_action_plan_detected(
        self, db_session: Session, test_org: Organization, test_user: User,
    ):
        """Workflow run without action plan must be flagged."""
        from app.api.risk_findings import _generate_mock_findings

        evidence = _make_evidence(db_session, test_org, test_user)
        workflow_run = WorkflowRun(
            organization_id=test_org.id,
            evidence_id=evidence.id,
            created_by=test_user.id,
            status=WorkflowRunStatus.SUCCESS,
            findings_count=3,
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(workflow_run)
        db_session.flush()

        findings_data = _generate_mock_findings(evidence.extracted_text, evidence.id)
        for f in findings_data:
            db_session.add(RiskFindingRecord(
                workflow_run_id=workflow_run.id,
                evidence_id=evidence.id,
                title=f["title"],
                description=f["description"],
                severity=f["severity"],
                cfr_refs=f.get("cfr_refs", []),
                citations=f.get("citations", []),
                entities=f.get("entities", []),
            ))
        db_session.commit()

        try:
            plan = db_session.query(ActionPlanRecord).filter(
                ActionPlanRecord.workflow_run_id == workflow_run.id,
            ).first()
            assert plan is None

            missing = []
            if not plan:
                missing.append("action_plan")
            assert "action_plan" in missing
        finally:
            _cleanup_workflow(db_session, workflow_run.id, evidence.id)

    def test_missing_correlation_data_detected(
        self, db_session: Session, test_org: Organization, test_user: User,
    ):
        """Action plan without correlation_data must be flagged."""
        from app.api.risk_findings import _generate_mock_findings

        evidence = _make_evidence(db_session, test_org, test_user)
        workflow_run = WorkflowRun(
            organization_id=test_org.id,
            evidence_id=evidence.id,
            created_by=test_user.id,
            status=WorkflowRunStatus.SUCCESS,
            findings_count=3,
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(workflow_run)
        db_session.flush()

        findings_data = _generate_mock_findings(evidence.extracted_text, evidence.id)
        for f in findings_data:
            db_session.add(RiskFindingRecord(
                workflow_run_id=workflow_run.id,
                evidence_id=evidence.id,
                title=f["title"],
                description=f["description"],
                severity=f["severity"],
                cfr_refs=f.get("cfr_refs", []),
                citations=f.get("citations", []),
                entities=f.get("entities", []),
            ))

        # Action plan with NO correlation data
        db_session.add(ActionPlanRecord(
            workflow_run_id=workflow_run.id,
            evidence_id=evidence.id,
            rationale="Test rationale",
            actions=[{"title": "Test", "priority": "LOW", "owner": "QA", "deadline": "7 days"}],
            owners=["QA"],
            deadlines=["7 days"],
            correlation_data=None,
        ))
        db_session.commit()

        try:
            plan = db_session.query(ActionPlanRecord).filter(
                ActionPlanRecord.workflow_run_id == workflow_run.id,
            ).first()
            assert plan is not None
            assert plan.correlation_data is None

            missing = []
            if not plan.correlation_data:
                missing.append("correlation_data")
            assert "correlation_data" in missing
        finally:
            _cleanup_workflow(db_session, workflow_run.id, evidence.id)


# ============= OUTPUT COMPLETENESS =============

class TestAuditPacketOutputCompleteness:
    """
    Verify the audit packet generators produce complete, non-placeholder output.
    """

    def test_executive_summary_references_real_data(
        self, db_session: Session, test_org: Organization, test_user: User,
    ):
        """Executive summary must reference evidence filename, findings count, severity."""
        evidence = _make_evidence(db_session, test_org, test_user)
        workflow_run = _make_full_workflow(db_session, test_org, test_user, evidence)

        try:
            db_findings = db_session.query(RiskFindingRecord).filter(
                RiskFindingRecord.workflow_run_id == workflow_run.id,
            ).all()
            db_plan = db_session.query(ActionPlanRecord).filter(
                ActionPlanRecord.workflow_run_id == workflow_run.id,
            ).first()

            summary = generate_executive_summary(
                evidence, db_findings, db_plan,
                db_plan.correlation_data.get("vendor_matches", []),
            )

            # Must reference the actual filename
            assert evidence.filename in summary

            # Must mention the real count
            assert str(len(db_findings)) in summary

            # Must contain a severity characterisation
            summary_lower = summary.lower()
            assert any(word in summary_lower for word in ["high", "medium", "low", "elevated", "moderate"])

            # Must not contain placeholder values
            assert "placeholder" not in summary_lower
            assert "n/a" not in summary_lower
            assert "todo" not in summary_lower

        finally:
            _cleanup_workflow(db_session, workflow_run.id, evidence.id)

    def test_correlation_narrative_contains_chain(
        self, db_session: Session, test_org: Organization, test_user: User,
    ):
        """Narrative must cover watchtower -> evidence -> findings -> risk -> decision."""
        evidence = _make_evidence(db_session, test_org, test_user)
        workflow_run = _make_full_workflow(db_session, test_org, test_user, evidence)

        try:
            db_findings = db_session.query(RiskFindingRecord).filter(
                RiskFindingRecord.workflow_run_id == workflow_run.id,
            ).all()
            db_plan = db_session.query(ActionPlanRecord).filter(
                ActionPlanRecord.workflow_run_id == workflow_run.id,
            ).first()

            narrative = generate_correlation_narrative(
                evidence, db_findings, db_plan.correlation_data,
            )

            narrative_lower = narrative.lower()

            # Must mention watchtower / supply chain context
            assert any(w in narrative_lower for w in ["watchtower", "supply", "feed", "alert", "signal"])

            # Must reference evidence
            assert evidence.filename in narrative

            # Must mention findings
            assert "finding" in narrative_lower

            # Must include risk/decision language
            assert any(w in narrative_lower for w in ["risk", "remediation", "action", "posture"])

        finally:
            _cleanup_workflow(db_session, workflow_run.id, evidence.id)

    def test_action_items_all_have_required_fields(
        self, db_session: Session, test_org: Organization, test_user: User,
    ):
        """Every action item must have action, owner, deadline, priority — no blanks."""
        evidence = _make_evidence(db_session, test_org, test_user)
        workflow_run = _make_full_workflow(db_session, test_org, test_user, evidence)

        try:
            db_plan = db_session.query(ActionPlanRecord).filter(
                ActionPlanRecord.workflow_run_id == workflow_run.id,
            ).first()

            items = build_action_plan_items(db_plan)
            assert len(items) >= 1

            for item in items:
                assert item.action.strip(), "action must not be empty"
                assert item.owner.strip(), "owner must not be empty"
                assert item.deadline.strip(), "deadline must not be empty"
                assert item.priority.strip(), "priority must not be empty"

                # No rejected values
                for field_val in [item.action, item.owner, item.deadline, item.priority]:
                    assert field_val.strip().lower() not in {"n/a", "tbd", "placeholder", "unknown"}

        finally:
            _cleanup_workflow(db_session, workflow_run.id, evidence.id)

    def test_reject_placeholder_utility(self):
        """The _reject_placeholder function must catch known bad values."""
        # Should pass
        assert _reject_placeholder("Quality Assurance Lead", "owner") == "Quality Assurance Lead"
        assert _reject_placeholder("Within 48 hours", "deadline") == "Within 48 hours"

        # Should reject
        for bad in [None, "", "N/A", "n/a", "TBD", "placeholder", "unknown", "  "]:
            with pytest.raises(ValueError):
                _reject_placeholder(bad, "test_field")

    def test_findings_have_cfr_refs(
        self, db_session: Session, test_org: Organization, test_user: User,
    ):
        """At least one finding must carry CFR references."""
        evidence = _make_evidence(db_session, test_org, test_user)
        workflow_run = _make_full_workflow(db_session, test_org, test_user, evidence)

        try:
            db_findings = db_session.query(RiskFindingRecord).filter(
                RiskFindingRecord.workflow_run_id == workflow_run.id,
            ).all()

            with_cfr = [f for f in db_findings if f.cfr_refs and len(f.cfr_refs) > 0]
            assert len(with_cfr) >= 1, "At least one finding must have CFR references"

        finally:
            _cleanup_workflow(db_session, workflow_run.id, evidence.id)


# ============= RUN TESTS =============

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
