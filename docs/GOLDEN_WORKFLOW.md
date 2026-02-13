# Golden Workflow End-to-End Verification

## Overview

The Golden Workflow has been enhanced to be fully end-to-end reliable, with persistent database storage for all workflow data.

## New Features

### 1. Workflow Run Persistence
- New `workflow_runs` table tracks each workflow execution
- `risk_findings_records` table stores findings from each run
- `action_plans` table stores action plans with correlation data

### 2. New API Endpoints

#### Run Complete Workflow (NEW)
```
POST /api/risk/workflow/run?evidence_id={id}
```
Runs the entire workflow end-to-end:
- Validates evidence is processed
- Generates findings
- Generates correlation with Watchtower
- Generates action plan
- Persists everything to database

**Response:**
```json
{
  "workflow_run_id": 1,
  "evidence_id": 1,
  "status": "success",
  "findings_count": 2,
  "correlations_count": 0,
  "actions_count": 1,
  "created_at": "2026-01-21T16:45:51.254607+00:00",
  "message": "Workflow completed: 2 findings, 1 actions"
}
```

#### List Workflow Runs
```
GET /api/risk/workflow/runs?evidence_id={id}&limit=10
```

#### Get Workflow Run Details
```
GET /api/risk/workflow/runs/{run_id}
```
Returns full details including findings, action plan, and correlation data.

#### Enhanced Export Packet
```
GET /api/risk/export-packet/{evidence_id}?run_id={optional}
```
Now pulls **REAL data** from the database. If `run_id` is not specified, uses the latest successful run.

### 3. Frontend Updates
- New "Run Complete Workflow (End-to-End)" button in Step 2
- Displays workflow run ID and status
- Export now includes the run ID for audit trail

## Verification Steps

### PowerShell Verification Script
```powershell
# 1. Login
$body = '{"email":"billhill@yahoo.com","password":"Test123!"}'
$response = Invoke-RestMethod -Uri "http://localhost:8001/api/auth/login" -Method POST -ContentType "application/json" -Body $body
$token = $response.access_token

# 2. List evidence
$headers = @{Authorization = "Bearer $token"}
$evidence = Invoke-RestMethod -Uri "http://localhost:8001/api/evidence" -Method GET -Headers $headers
Write-Output "Evidence ID: $($evidence.id)"

# 3. Run complete workflow
$result = Invoke-RestMethod -Uri "http://localhost:8001/api/risk/workflow/run?evidence_id=$($evidence.id)" -Method POST -Headers $headers
Write-Output "Workflow Run ID: $($result.workflow_run_id), Status: $($result.status)"

# 4. Get workflow run details
$details = Invoke-RestMethod -Uri "http://localhost:8001/api/risk/workflow/runs/$($result.workflow_run_id)" -Method GET -Headers $headers
Write-Output "Findings: $($details.findings_count), Actions: $($details.actions_count)"

# 5. Export audit packet
$export = Invoke-WebRequest -Uri "http://localhost:8001/api/risk/export-packet/$($evidence.id)" -Method GET -Headers $headers -UseBasicParsing
Write-Output "Export filename: $($export.Headers['Content-Disposition'])"
Write-Output "Export length: $($export.Content.Length) bytes"
```

### Expected Results
- ✅ Workflow completes with status "success"
- ✅ Findings persisted to `risk_findings_records` table
- ✅ Action plan persisted to `action_plans` table
- ✅ Correlation data stored in action_plan's `correlation_data` JSON column
- ✅ Export contains workflow run ID and pulls from database
- ✅ Audit log entries created for workflow operations

## Database Schema

### workflow_runs
- `id` - Primary key
- `organization_id` - FK to organizations
- `evidence_id` - FK to evidence
- `created_by` - FK to users
- `status` - enum: pending, running, success, failed
- `error_message` - Text, nullable
- `findings_count` - Integer
- `correlations_count` - Integer
- `actions_count` - Integer
- `created_at` - Timestamp
- `completed_at` - Timestamp, nullable

### risk_findings_records
- `id` - Primary key
- `workflow_run_id` - FK to workflow_runs
- `evidence_id` - FK to evidence
- `title` - String
- `description` - Text
- `severity` - String (LOW, MEDIUM, HIGH)
- `cfr_refs` - JSON array
- `citations` - JSON array
- `entities` - JSON array
- `created_at` - Timestamp

### action_plans
- `id` - Primary key
- `workflow_run_id` - FK to workflow_runs
- `evidence_id` - FK to evidence
- `rationale` - Text
- `actions` - JSON array
- `owners` - JSON array
- `deadlines` - JSON array
- `correlation_data` - JSON object (contains Watchtower snapshot, vendor matches, narrative)
- `created_at` - Timestamp
