"""
Workflow execution Celery tasks — Golden Workflow (findings + correlation + action plan).
"""
from app.core.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(bind=True, name="workflow.run_complete")
def run_complete_workflow(self, evidence_id: int, org_id: int, user_id: int, workflow_run_id: int):
    """Execute the full Golden Workflow end-to-end as a background task.

    Steps:
    1. Generate compliance findings from evidence text
    2. Correlate findings with Watchtower supply-chain data
    3. Generate a prioritised action plan
    4. Persist everything to the database under the given WorkflowRun
    """
    from datetime import datetime, timezone
    from app.db.session import get_db_context
    from app.db.models import (
        Evidence, WorkflowRun, WorkflowRunStatus,
        RiskFindingRecord, ActionPlanRecord, AuditLog,
    )
    from app.api.risk_findings import (
        _generate_mock_findings, _generate_correlation, _generate_action_plan,
    )
    from app.core.metrics import WORKFLOW_RUNS_TOTAL

    with get_db_context() as db:
        evidence = db.query(Evidence).filter(
            Evidence.id == evidence_id,
            Evidence.organization_id == org_id,
        ).first()
        if not evidence:
            return {"status": "error", "detail": "Evidence not found"}

        workflow_run = db.query(WorkflowRun).filter(
            WorkflowRun.id == workflow_run_id,
        ).first()
        if not workflow_run:
            return {"status": "error", "detail": "WorkflowRun not found"}

        try:
            # 1. Generate findings
            findings_data = _generate_mock_findings(evidence.extracted_text, evidence_id)
            for f in findings_data:
                db.add(RiskFindingRecord(
                    workflow_run_id=workflow_run.id,
                    evidence_id=evidence_id,
                    title=f.get("title", ""),
                    description=f.get("description", ""),
                    severity=f.get("severity", "MEDIUM"),
                    cfr_refs=f.get("cfr_refs", []),
                    citations=f.get("citations", []),
                    entities=f.get("entities", []),
                ))
            workflow_run.findings_count = len(findings_data)

            # 2. Correlate with Watchtower data
            correlation = _generate_correlation(evidence, findings_data, db, org_id)
            workflow_run.correlations_count = len(correlation.get("vendor_matches", []))

            # 3. Generate action plan
            plan_data = _generate_action_plan(
                findings_data, None, correlation.get("vendor_matches", []),
            )
            db.add(ActionPlanRecord(
                workflow_run_id=workflow_run.id,
                evidence_id=evidence_id,
                rationale=plan_data.get("rationale", ""),
                actions=plan_data.get("top_actions", []),
                owners=plan_data.get("owners", []),
                deadlines=plan_data.get("deadlines", []),
                correlation_data=correlation,
            ))
            workflow_run.actions_count = len(plan_data.get("top_actions", []))

            # Mark success
            workflow_run.status = WorkflowRunStatus.SUCCESS
            workflow_run.completed_at = datetime.now(timezone.utc)

            db.add(AuditLog(
                organization_id=org_id,
                user_id=user_id,
                action="workflow_run_completed",
                entity_type="workflow_run",
                entity_id=workflow_run.id,
                details={
                    "evidence_id": evidence_id,
                    "findings_count": workflow_run.findings_count,
                    "correlations_count": workflow_run.correlations_count,
                    "actions_count": workflow_run.actions_count,
                },
            ))

            WORKFLOW_RUNS_TOTAL.labels(status="success").inc()
            logger.info(
                "Workflow run completed",
                extra={
                    "service": "risk_findings",
                    "event": "workflow_execution",
                    "workflow_run_id": workflow_run.id,
                    "evidence_id": evidence_id,
                    "findings_count": workflow_run.findings_count,
                },
            )

            return {
                "workflow_run_id": workflow_run.id,
                "evidence_id": evidence_id,
                "status": "success",
                "findings_count": workflow_run.findings_count,
                "correlations_count": workflow_run.correlations_count,
                "actions_count": workflow_run.actions_count,
            }

        except Exception as e:
            workflow_run.status = WorkflowRunStatus.FAILED
            workflow_run.error_message = str(e)
            workflow_run.completed_at = datetime.now(timezone.utc)

            WORKFLOW_RUNS_TOTAL.labels(status="failed").inc()
            logger.error(
                f"Workflow run {workflow_run.id} failed: {e}",
                extra={
                    "service": "risk_findings",
                    "event": "workflow_execution",
                    "workflow_run_id": workflow_run.id,
                    "evidence_id": evidence_id,
                },
            )
            return {
                "workflow_run_id": workflow_run.id,
                "status": "failed",
                "error": str(e),
            }
