# Golden Workflow Verification Instructions

This document provides exact commands to verify the Golden Workflow end-to-end reliability.

## Prerequisites

1. Application is running:
   ```bash
   docker-compose up -d
   ```

2. Obtain authentication token:
   ```bash
   # Login and capture token
   curl -s -X POST http://localhost:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email": "admin@pharmaforge.local", "password": "admin123"}' | jq -r '.access_token'
   ```

   Set the token as an environment variable:
   ```bash
   export TOKEN="<your_token_here>"
   ```

---

## Step 1: Health Check

**Verify Golden Workflow is ready:**

```bash
curl -s http://localhost:8000/api/risk/health/golden-workflow | jq
```

**Expected Response (when ready):**
```json
{
  "ready": true,
  "blocking_reason": null,
  "details": {
    "evidence": {
      "total": 1,
      "processed": 1,
      "pending": 0,
      "processing": 0,
      "failed": 0
    },
    "workflow_runs": {
      "total": 0,
      "successful": 0,
      "failed": 0
    }
  }
}
```

**If `ready: false`**, the `blocking_reason` will explain what's missing.

---

## Step 2: Evidence Upload

**Create a test PDF or TXT file:**

```bash
cat > /tmp/test_evidence.txt << 'EOF'
PHARMACEUTICAL COMPLIANCE ASSESSMENT

Temperature Control Assessment:
Cold chain storage procedures have been reviewed. Temperature monitoring
revealed deviations from the 2-8C storage requirements for API materials.

Vendor Assessment:
Supplier XYZ Pharma Labs has been evaluated for cGMP compliance.
Manufacturing practices require additional qualification audits.

Labeling Review:
Product labeling must be updated to include serialization requirements
per DSCSA Section 582 traceability mandates.

Recall History:
Previous quality deviation on Lot #2023-001 has been resolved.
CAPA documentation is complete.
EOF
```

**Upload evidence:**

```bash
curl -s -X POST http://localhost:8000/api/evidence \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test_evidence.txt" | jq
```

**Expected Response:**
```json
{
  "id": 1,
  "filename": "test_evidence.txt",
  "sha256": "<hash>",
  "status": "processed",
  "created_at": "<timestamp>",
  "message": "File uploaded and processed successfully"
}
```

**CRITICAL CHECKS:**
- `status` MUST be `"processed"` (not `"pending"` or `"failed"`)
- If `status` is `"failed"`, check `message` for error details

**Save the evidence ID:**
```bash
export EVIDENCE_ID=1
```

---

## Step 3: Run Golden Workflow

**Execute the workflow:**

```bash
curl -s -X POST "http://localhost:8000/api/risk/workflow/run?evidence_id=$EVIDENCE_ID" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Expected Response:**
```json
{
  "workflow_run_id": 1,
  "evidence_id": 1,
  "status": "success",
  "findings_count": 5,
  "correlations_count": 0,
  "actions_count": 4,
  "created_at": "<timestamp>",
  "message": "Workflow completed: 5 findings, 4 actions"
}
```

**CRITICAL CHECKS:**
- `status` MUST be `"success"`
- `findings_count` MUST be >= 1
- `actions_count` MUST be >= 1
- `workflow_run_id` MUST be a valid integer

**Save the workflow run ID:**
```bash
export RUN_ID=1
```

**Error Cases (should return 400):**

If evidence is not processed:
```json
{
  "detail": {
    "error": "evidence_not_processed",
    "message": "Evidence is still pending processing...",
    "status": "pending"
  }
}
```

---

## Step 4: Export Audit Packet

**Export the audit packet:**

```bash
curl -s "http://localhost:8000/api/risk/export-packet/$EVIDENCE_ID?run_id=$RUN_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -o /tmp/audit_packet.md

cat /tmp/audit_packet.md
```

**Expected Output Structure:**

The markdown file MUST contain ALL of these sections:

```markdown
# Audit Packet: test_evidence.txt
**Workflow Run ID: 1**
Generated: <timestamp>

---

## Workflow Run Information
- **Workflow Run ID**: 1
- **Status**: success
- **Run Created At**: <timestamp>
- **Run Completed At**: <timestamp>

---

## 1. Evidence Metadata
- **ID**: 1
- **Filename**: test_evidence.txt
- **SHA256**: <hash>
...

---

## 2. Compliance Findings
**5 finding(s) identified from this workflow run.**

### Finding 1: Cold Chain Storage Compliance Gap
- **Severity**: HIGH
- **Description**: Document references temperature-sensitive storage...
- **CFR References**: 21 CFR 211.142, 21 CFR 211.150
- **Citations**: 'temperature' mentioned in source document
...

---

## 3. Watchtower Correlation

### Supply Chain Intelligence Snapshot
- **Total Feed Items**: <count>
- **Active Alerts**: <count>
...

### Risk Narrative (Watchtower -> Evidence -> Risk Correlation)
- <bullet points>
...

---

## 4. Action Plan
**Rationale**: Action plan generated based on 5 compliance finding(s)...

### Actions:

#### 1. Investigate: Cold Chain Storage Compliance Gap
- **Priority**: HIGH
- **Description**: Address finding...
- **Owner**: Quality Assurance Lead
- **Deadline**: Within 48 hours
...

---

## 5. Audit Log
| Timestamp | Action | Details |
|-----------|--------|---------|
...
```

**CRITICAL CHECKS:**
- Workflow Run ID MUST be present (NOT "N/A")
- Findings section MUST have at least 1 finding with CFR references
- Correlation section MUST have narrative bullets
- Action Plan MUST have at least 1 action with owner and deadline
- NO "N/A" placeholders except where data is genuinely not available

---

## Step 5: Error Case Verification

### 5a. Export without workflow run (should fail)

```bash
# Create new evidence
curl -s -X POST http://localhost:8000/api/evidence \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test_evidence.txt" | jq

# Immediately try to export (without running workflow)
curl -s "http://localhost:8000/api/risk/export-packet/2" \
  -H "Authorization: Bearer $TOKEN" | jq
```

**Expected Error Response (400):**
```json
{
  "detail": {
    "error": "no_workflow_run",
    "message": "No successful workflow run found. Run POST /api/risk/workflow/run first.",
    "evidence_id": 2,
    "action_required": "POST /api/risk/workflow/run?evidence_id=2"
  }
}
```

### 5b. Workflow with unprocessed evidence (should fail)

First, simulate unprocessed evidence by checking the database directly or using the API:

```bash
# This would fail if evidence.status != "processed"
# The endpoint returns 400 with structured error
```

---

## Step 6: Run Tests

**Run the Golden Workflow test suite:**

```bash
cd /app
python -m pytest app/tests/test_golden_workflow.py -v --tb=short
```

**Expected Output:**
```
app/tests/test_golden_workflow.py::TestWorkflowBlocksUnprocessedEvidence::test_workflow_rejects_pending_evidence PASSED
app/tests/test_golden_workflow.py::TestWorkflowBlocksUnprocessedEvidence::test_workflow_rejects_processing_evidence PASSED
app/tests/test_golden_workflow.py::TestWorkflowBlocksUnprocessedEvidence::test_workflow_rejects_failed_evidence PASSED
app/tests/test_golden_workflow.py::TestWorkflowBlocksUnprocessedEvidence::test_workflow_accepts_only_processed_evidence PASSED
app/tests/test_golden_workflow.py::TestExportPacketFieldValidation::test_export_requires_workflow_run PASSED
app/tests/test_golden_workflow.py::TestExportPacketFieldValidation::test_export_requires_findings PASSED
app/tests/test_golden_workflow.py::TestExportPacketFieldValidation::test_export_requires_action_plan PASSED
app/tests/test_golden_workflow.py::TestExportPacketFieldValidation::test_export_requires_correlation PASSED
app/tests/test_golden_workflow.py::TestWarCouncilOutputValidation::test_action_plan_rationale_not_empty PASSED
app/tests/test_golden_workflow.py::TestWarCouncilOutputValidation::test_action_plan_has_actions_with_owners PASSED
app/tests/test_golden_workflow.py::TestWarCouncilOutputValidation::test_action_plan_has_deadlines PASSED
app/tests/test_golden_workflow.py::TestWarCouncilOutputValidation::test_correlation_narrative_not_empty PASSED
```

**All tests MUST pass.** If any test fails, the Golden Workflow is NOT reliable.

---

## Summary Checklist

| Step | Endpoint | Expected |
|------|----------|----------|
| Health Check | `GET /api/risk/health/golden-workflow` | `{"ready": true}` |
| Upload Evidence | `POST /api/evidence` | `{"status": "processed"}` |
| Run Workflow | `POST /api/risk/workflow/run` | `{"status": "success"}` |
| Export Packet | `GET /api/risk/export-packet/{id}` | Markdown with all sections |
| Export w/o Run | `GET /api/risk/export-packet/{id}` (no run) | 400 error with `no_workflow_run` |
| Tests | `pytest app/tests/test_golden_workflow.py` | All PASSED |

---

## Troubleshooting

### Evidence stuck in "pending"
- Check if text extraction failed
- Review application logs: `docker-compose logs api`

### Workflow returns 400
- Verify evidence status is "processed"
- Check evidence has extracted_text

### Export returns empty sections
- This should NOT happen after stabilization
- If it does, it indicates a data integrity issue
- Run the test suite to identify the failure

### Database connection issues
- Verify PostgreSQL is running: `docker-compose ps`
- Check database logs: `docker-compose logs db`
