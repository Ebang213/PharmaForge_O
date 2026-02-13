# Verification Checklist - Watchtower & DSCSA/EPCIS

This document provides verification steps for the Watchtower live feed and DSCSA/EPCIS validation functionality.

---

## Quick Start Verification

Run the automated verification script:

```powershell
cd C:\Users\eugene\Documents\PharmaForge_OS

# Seed demo data (3 vendors, 1 facility, 1 sample evidence)
python -m scripts.seed_demo_data

# Watchtower verification
.\scripts\verify_watchtower.ps1

# Full stack verification (Watchtower + DSCSA)
.\scripts\verify.ps1
```

---

## 🔄 Golden Loop Verification (Risk Intelligence Loop)

This section verifies the complete end-to-end product loop:
**Compliance Copilot findings → Watchtower correlation → Decision Council plan → Exportable audit packet**

### Prerequisites

1. Seed demo data:
   ```powershell
   python -m scripts.seed_demo_data
   ```

2. Start the stack:
   ```powershell
   docker-compose up -d
   ```

### PowerShell Verification

```powershell
# ===== STEP 1: Login =====
$body = @{ email = "admin@acmepharma.com"; password = "admin123" } | ConvertTo-Json
$login = Invoke-RestMethod -Uri "http://localhost:8001/api/auth/login" -Method POST -Body $body -ContentType "application/json"
$headers = @{ Authorization = "Bearer $($login.access_token)" }
Write-Host "✓ Logged in. Token acquired."

# ===== STEP 2: Upload Evidence =====
$evidenceFile = ".\samples\pdfs\sample_guidance.txt"
$uploadResult = curl.exe -s -X POST "http://localhost:8001/api/evidence" `
  -H "Authorization: Bearer $($login.access_token)" `
  -F "file=@$evidenceFile"
$evidence = $uploadResult | ConvertFrom-Json
$evidenceId = $evidence.id
Write-Host "✓ Evidence uploaded. ID: $evidenceId"

# ===== STEP 3: Run Findings =====
$findings = Invoke-RestMethod -Uri "http://localhost:8001/api/risk/findings/run?evidence_id=$evidenceId" -Method POST -Headers $headers
Write-Host "✓ Findings generated: $($findings.findings.Count) findings"

# ===== STEP 4: Correlate with Watchtower (REAL correlation output) =====
$correlateBody = @{ evidence_id = $evidenceId } | ConvertTo-Json
$correlation = Invoke-RestMethod -Uri "http://localhost:8001/api/risk/correlate" -Method POST -Body $correlateBody -Headers $headers -ContentType "application/json"
Write-Host "✓ Correlation complete."
Write-Host "  - Feed items monitored: $($correlation.watchtower_snapshot.total_feed_items)"
Write-Host "  - Active alerts: $($correlation.watchtower_snapshot.active_alerts)"
Write-Host "  - Vendor matches: $($correlation.vendor_matches.Count)"
Write-Host "  - Correlation timestamp: $($correlation.correlation_timestamp)"
Write-Host "  - Risk Narrative:"
$correlation.narrative | ForEach-Object { Write-Host "    - $_" }

# ===== STEP 5: Generate Action Plan =====
$planBody = @{
    evidence_id = $evidenceId
    findings = $findings.findings
} | ConvertTo-Json -Depth 5
$plan = Invoke-RestMethod -Uri "http://localhost:8001/api/risk/warcouncil/plan" -Method POST -Body $planBody -Headers $headers -ContentType "application/json"
Write-Host "✓ Action plan generated: $($plan.top_actions.Count) actions"

# ===== STEP 6: Export Audit Packet (Downloads as file) =====
# The endpoint returns a Markdown file with Content-Disposition header
$packetResponse = Invoke-WebRequest -Uri "http://localhost:8001/api/risk/export-packet/$evidenceId" -Headers $headers
$packetResponse.Content | Out-File -FilePath ".\audit_packet_$evidenceId.md" -Encoding UTF8
Write-Host "✓ Audit packet exported to: audit_packet_$evidenceId.md"
Write-Host "  - Content-Type: $($packetResponse.Headers['Content-Type'])"

# ===== STEP 7: Verify Audit Log Contains correlation_generated =====
$auditLogs = Invoke-RestMethod -Uri "http://localhost:8001/api/audit/logs?entity_type=evidence&entity_id=$evidenceId" -Headers $headers
Write-Host "✓ Audit log entries for evidence $evidenceId:"
$auditLogs | ForEach-Object { Write-Host "    - $($_.action) at $($_.timestamp)" }

# ===== STEP 8: Verify Health Endpoints (Auth Required) =====
$riskHealth = Invoke-RestMethod -Uri "http://localhost:8001/api/risk/health" -Headers $headers
$wtHealth = Invoke-RestMethod -Uri "http://localhost:8001/api/watchtower/health" -Headers $headers
Write-Host "✓ Risk module: $($riskHealth.status)"
Write-Host "✓ Watchtower module: $($wtHealth.status)"

Write-Host "`n=========================================="
Write-Host "GOLDEN LOOP VERIFICATION COMPLETE ✓"
Write-Host "=========================================="
```

### curl Verification (Linux/Mac/WSL)

```bash
# Variables
BASE_URL="http://localhost:8001"

# Step 1: Login
TOKEN=$(curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@acmepharma.com","password":"admin123"}' | jq -r '.access_token')
echo "✓ Logged in"

# Step 2: Upload Evidence
EVIDENCE=$(curl -s -X POST "$BASE_URL/api/evidence" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@./samples/pdfs/sample_guidance.txt")
EVIDENCE_ID=$(echo $EVIDENCE | jq -r '.id')
echo "✓ Evidence uploaded. ID: $EVIDENCE_ID"

# Step 3: Run Findings
FINDINGS=$(curl -s -X POST "$BASE_URL/api/risk/findings/run?evidence_id=$EVIDENCE_ID" \
  -H "Authorization: Bearer $TOKEN")
echo "✓ Findings: $(echo $FINDINGS | jq '.findings | length')"

# Step 4: Correlate with Watchtower (REAL correlation)
CORRELATION=$(curl -s -X POST "$BASE_URL/api/risk/correlate" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"evidence_id\": $EVIDENCE_ID}")
echo "✓ Correlation complete"
echo "  Feed items: $(echo $CORRELATION | jq '.watchtower_snapshot.total_feed_items')"
echo "  Active alerts: $(echo $CORRELATION | jq '.watchtower_snapshot.active_alerts')"
echo "  Vendor matches: $(echo $CORRELATION | jq '.vendor_matches | length')"
echo "  Correlation timestamp: $(echo $CORRELATION | jq -r '.correlation_timestamp')"
echo "  Risk Narrative:"
echo $CORRELATION | jq -r '.narrative[]' | while read line; do echo "    - $line"; done

# Step 5: Generate Action Plan
PLAN=$(curl -s -X POST "$BASE_URL/api/risk/warcouncil/plan" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"evidence_id\": $EVIDENCE_ID, \"findings\": $(echo $FINDINGS | jq '.findings')}")
echo "✓ Plan: $(echo $PLAN | jq '.top_actions | length') actions"

# Step 6: Export Audit Packet (file download with Content-Disposition)
curl -s "$BASE_URL/api/risk/export-packet/$EVIDENCE_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -o "audit_packet_$EVIDENCE_ID.md" \
  -D -
echo "✓ Exported: audit_packet_$EVIDENCE_ID.md"

# Step 7: Verify audit log contains correlation_generated
curl -s "$BASE_URL/api/audit/logs?entity_type=evidence&entity_id=$EVIDENCE_ID" \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | {action, timestamp}'

# Step 8: Health checks (require auth)
curl -s "$BASE_URL/api/risk/health" -H "Authorization: Bearer $TOKEN" | jq
curl -s "$BASE_URL/api/watchtower/health" -H "Authorization: Bearer $TOKEN" | jq
```

### Expected Outputs

#### Correlation Response (Step 4)
```json
{
  "evidence_id": 1,
  "watchtower_snapshot": {
    "total_feed_items": 42,
    "active_alerts": 3,
    "sources_status": [{"source": "fda_recalls", "healthy": true}],
    "top_items": [{"title": "FDA Recall...", "category": "recall"}],
    "timestamp": "2026-01-15T10:30:00Z"
  },
  "vendor_matches": [
    {"vendor_id": 1, "name": "Acme Pharma", "match_basis": "text_content", "risk_level": "medium"}
  ],
  "narrative": [
    "🔴 2 HIGH severity finding(s) require immediate attention.",
    "⚠️ 3 active Watchtower alert(s) may indicate supply chain exposure.",
    "📡 Watchtower is monitoring 42 FDA feed item(s) for correlation."
  ],
  "correlation_timestamp": "2026-01-15T10:30:00Z"
}
```

#### Audit Log Actions (Step 7)
Expected audit log entries for the evidence:
- `findings_generated` - When findings were extracted
- `correlation_generated` - When Watchtower correlation was run
- `action_plan_generated` - When action plan was created
- `audit_packet_exported` - When audit packet was downloaded

### Expected Audit Packet Contents

After export, the Markdown file should contain:

1. **Evidence Metadata** - filename, SHA256, upload time, source
2. **Compliance Findings** - 3-10 findings with severity, CFR refs
3. **Watchtower Correlation** (NON-EMPTY):
   - Supply chain snapshot (feed items, alerts, timestamp)
   - Feed sources status table
   - Recent FDA feed items
   - Vendor matches table with risk scores
   - Risk narrative bullets (the key correlation output)
   - Correlation summary stats
4. **Action Plan** - prioritized actions with owners and deadlines
5. **Audit Log** - timestamped entries for all workflow steps

### Auth Verification

Verify that endpoints return 401 without token:

```powershell
# These should ALL fail with 401 Unauthorized
try { Invoke-RestMethod -Uri "http://localhost:8001/api/risk/health" }
catch { Write-Host "✓ /api/risk/health requires auth (401)" }

try { Invoke-RestMethod -Uri "http://localhost:8001/api/watchtower/health" }
catch { Write-Host "✓ /api/watchtower/health requires auth (401)" }

try { Invoke-RestMethod -Uri "http://localhost:8001/api/risk/correlate" -Method POST }
catch { Write-Host "✓ /api/risk/correlate requires auth (401)" }

try { Invoke-RestMethod -Uri "http://localhost:8001/api/risk/export-packet/1" }
catch { Write-Host "✓ /api/risk/export-packet requires auth (401)" }
```

```bash
# curl verification (should all return 401)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/risk/health
# Expected: 401

curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/risk/export-packet/1
# Expected: 401

curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8001/api/risk/correlate
# Expected: 401
```

---

## Watchtower Live Feed Verification

### 1. API Testing (PowerShell)

```powershell
# Login and store token
$body = @{ email = "admin@acmepharma.com"; password = "YourAdminPassword" } | ConvertTo-Json
$login = Invoke-RestMethod -Uri "http://localhost:8001/api/auth/login" -Method POST -Body $body -ContentType "application/json"
$headers = @{ Authorization = "Bearer $($login.access_token)" }

# 1. List feed sources
Invoke-RestMethod -Uri "http://localhost:8001/api/watchtower/sources" -Headers $headers

# Expected: Array of 3 sources with sync status
# [
#   { "source_id": "fda_recalls", "source_name": "FDA Drug Recalls", ... },
#   { "source_id": "fda_warning_letters", "source_name": "FDA Warning Letters", ... },
#   { "source_id": "fda_shortages", "source_name": "FDA Drug Shortages", ... }
# ]

# 2. Get live feed items
Invoke-RestMethod -Uri "http://localhost:8001/api/watchtower/feed?limit=10" -Headers $headers

# Expected: Array of feed items from FDA
# [{ "id": 1, "source": "fda_recalls", "title": "Recall: ...", "category": "recall" }]

# 3. Get feed summary
Invoke-RestMethod -Uri "http://localhost:8001/api/watchtower/feed/summary" -Headers $headers

# Expected: { "total_items": N, "by_source": {...}, "all_sources_healthy": true }

# 4. Get health status (detailed per-source status)
$health = Invoke-RestMethod -Uri "http://localhost:8001/api/watchtower/health" -Headers $headers
$health | ConvertTo-Json -Depth 4

# Expected output:
# {
#   "overall_status": "healthy",  // "healthy" | "degraded" | "down"
#   "sources": [
#     { "source_id": "fda_recalls", "status": "ok", "last_success_at": "2026-01-15T23:30:00", ... },
#     { "source_id": "fda_shortages", "status": "ok", ... },
#     { "source_id": "fda_warning_letters", "status": "ok", ... }
#   ],
#   "counts": { "feed_items": 150, "active_alerts": 0, "vendors": 3, "facilities": 1 },
#   "all_sources_healthy": true
# }

# Check that no sources are in error:
$health.sources | Where-Object { $_.status -eq "error" }
# Expected: (empty)

# 5. Trigger sync (Admin only)
Invoke-RestMethod -Uri "http://localhost:8001/api/watchtower/sync" -Method POST -Headers $headers

# Expected: { "status": "complete", "results": [{ "source": "fda_recalls", "items_fetched": N }] }
```

### 2. Evidence Uploads (PowerShell)

```powershell
# Upload evidence file (PDF or TXT)
$file = ".\samples\pdfs\sample_guidance.txt"
curl.exe -X POST "http://localhost:8001/api/watchtower/evidence" `
  -H "Authorization: Bearer $($login.access_token)" `
  -F "file=@$file" `
  -F "source_type=manual" `
  -F "notes=Watchtower evidence test"

# List Watchtower evidence
Invoke-RestMethod -Uri "http://localhost:8001/api/watchtower/evidence?limit=10" -Headers $headers
```

### 3. UI Testing

1. [ ] Navigate to **Watchtower** page
2. [ ] Verify "Feed Sources" section shows FDA Drug Recalls
3. [ ] Check source status indicator (green = healthy, red = error)
4. [ ] Click "Sync Now" button (visible only to Admin/Owner)
5. [ ] Verify feed items populate in the "Live Feed" tab
6. [ ] Items should show:
   - Category badge (RECALL)
   - Title with external link
   - Summary text
   - Published date
3. [ ] Check source status indicator (green = healthy, red = error)
4. [ ] Click "Sync Now" button (visible only to Admin/Owner)
5. [ ] Verify feed items populate in the "Live Feed" tab
6. [ ] Items should show:
   - Category badge (RECALL)
   - Title with external link
   - Summary text
   - Published date
7. [ ] Switch to "Alerts" tab
8. [ ] Verify empty state message if no alerts
9. [ ] Switch to **Evidence** tab
10. [ ] Upload a PDF/TXT and confirm it appears with a processed status

### 4. Error Handling

1. [ ] If feed is unreachable, UI shows "Live feed unavailable"
2. [ ] Source status shows error with message
3. [ ] Check API logs for detailed error information

---

## Golden Workflow Verification

### 1. API Testing (PowerShell)

```powershell
# Use token from login above
$headers = @{ Authorization = "Bearer $($login.access_token)" }

# 1. Check risk module health
Invoke-RestMethod -Uri "http://localhost:8001/api/risk/health" -Headers $headers
# Expected: { "status": "healthy", "module": "risk_findings" }

# 2. Upload evidence first (if not already)
$file = ".\samples\pdfs\sample_guidance.txt"
curl.exe -X POST "http://localhost:8001/api/evidence" `
  -H "Authorization: Bearer $($login.access_token)" `
  -F "file=@$file"
# Returns: { "id": 1, "filename": "...", "sha256": "..." }

# 3. Run findings extraction
Invoke-RestMethod -Uri "http://localhost:8001/api/risk/findings/run?evidence_id=1" -Method POST -Headers $headers
# Expected: { "evidence_id": 1, "findings": [...], "message": "Generated N compliance findings" }

# 4. Get stored findings
Invoke-RestMethod -Uri "http://localhost:8001/api/risk/findings?evidence_id=1" -Headers $headers
# Expected: Array of RiskFinding objects with CFR refs

# 5. Generate action plan
$planBody = @{
  evidence_id = 1
  findings = @(
    @{ title = "Test Finding"; severity = "HIGH"; cfr_refs = @("21 CFR 211") }
  )
} | ConvertTo-Json -Depth 3
Invoke-RestMethod -Uri "http://localhost:8001/api/risk/warcouncil/plan" -Method POST -Body $planBody -Headers $headers -ContentType "application/json"
# Expected: { "top_actions": [...], "rationale": "...", "owners": [...] }

# 6. Export audit packet
Invoke-RestMethod -Uri "http://localhost:8001/api/risk/export-packet/1" -Headers $headers
# Expected: { "filename": "audit_packet_1_20260110.md", "content": "# Audit Packet..." }
```

### 2. UI Testing

1. [ ] Navigate to **Mission Control** (`/mission-control`)
2. [ ] Verify "Start Here" button is visible at top
3. [ ] Click "Start Here" to go to `/workflow`
4. [ ] **Step 1 - Upload Evidence**:
   - [ ] Upload a PDF/TXT file or select existing
   - [ ] Confirm file appears in list
5. [ ] **Step 2 - Identify Findings**:
   - [ ] Click "Run Findings Extraction"
   - [ ] Wait for findings to appear
   - [ ] Verify findings show severity badges, CFR refs, citations
6. [ ] **Step 3 - Correlate Risks**:
   - [ ] Verify Watchtower summary loads
   - [ ] Verify high-risk vendors are listed (if any)
   - [ ] Confirm findings summary counts
7. [ ] **Step 4 - Action Plan**:
   - [ ] Click "Generate Action Plan"
   - [ ] Verify actions appear with priority, owner, deadline
   - [ ] Click "Export Audit Packet (Markdown)"
   - [ ] Confirm .md file downloads with full audit trail

### 3. Audit Log Entries

After completing the workflow, verify audit entries:

```powershell
Invoke-RestMethod -Uri "http://localhost:8001/api/audit/logs?entity_type=evidence" -Headers $headers
# Expected entries:
# - "evidence_uploaded"
# - "findings_generated"
# - "action_plan_generated"
```

---

## DSCSA/EPCIS Verification

### 1. Sample Files

Sample EPCIS files are located at `/samples/epcis/`:

| File | Format | Type | Expected Result |
|------|--------|------|-----------------|
| `valid.json` | JSON | Full supply chain | VALID |
| `object_event.xml` | XML | ObjectEvent | VALID |
| `aggregation_event.xml` | XML | AggregationEvent | VALID |
| `broken.json` | JSON | Malformed | INVALID |

### 2. API Testing (PowerShell)

```powershell
# Use token from login above
$headers = @{ Authorization = "Bearer $($login.access_token)" }

# 1. Upload EPCIS file
$file = ".\samples\epcis\valid.json"
curl.exe -X POST "http://localhost:8001/api/dscsa/epcis/upload" `
  -H "Authorization: Bearer $($login.access_token)" `
  -F "file=@$file"

# Expected: Upload details with validation results
# { "id": 1, "validation_status": "valid", "event_count": 5, "issues": [...] }

# 2. List uploads
Invoke-RestMethod -Uri "http://localhost:8001/api/dscsa/epcis/uploads" -Headers $headers

# 3. Get upload details
Invoke-RestMethod -Uri "http://localhost:8001/api/dscsa/epcis/uploads/1" -Headers $headers

# 4. Download audit packet
Invoke-RestMethod -Uri "http://localhost:8001/api/dscsa/uploads/1/audit-packet" -Headers $headers
```

### 3. UI Testing

1. [ ] Navigate to **DSCSA / EPCIS** page
2. [ ] Click "Upload File" and select `samples/epcis/valid.json`
3. [ ] Verify upload appears in "Recent Uploads" list
4. [ ] Click upload to view details
5. [ ] Check **Validation Details**:
   - Status badge (VALID/INVALID/CHAIN_BREAK)
   - Event count
   - Chain break count
   - Issues list with severity colors
6. [ ] Check **Parsed Events** table:
   - Event type (ObjectEvent, AggregationEvent)
   - Action (ADD, OBSERVE, DELETE)
   - Event time
   - EPC count
   - Biz Step (last segment)
   - Location
7. [ ] Click "Audit Packet" to download JSON bundle

### 4. Validation Rules Tested

- [x] eventTime is required (high severity if missing)
- [x] eventType must be valid (ObjectEvent, AggregationEvent, etc.)
- [x] action required for most event types
- [x] epcList or quantityList required (critical severity)
- [x] EPC format validation (URN format)
- [x] Chain break detection (temporal order, duplicate DELETE)

---

## Auth Verification

### Endpoints Require JWT

All these endpoints should return **401 Unauthorized** without token:

```powershell
# Without Authorization header - should fail with 401
Invoke-RestMethod -Uri "http://localhost:8001/api/watchtower/feed"
# Expected: 401 Unauthorized

Invoke-RestMethod -Uri "http://localhost:8001/api/watchtower/sources"
# Expected: 401 Unauthorized

Invoke-RestMethod -Uri "http://localhost:8001/api/dscsa/epcis/uploads"
# Expected: 401 Unauthorized
```

### Frontend Token Handling

1. [ ] All API calls include `Authorization: Bearer <token>` header
2. [ ] On 401 response, user is redirected to `/login`
3. [ ] Token is stored in `localStorage` as `pharmaforge_token`

---

## Database Migration

Before running, ensure migration is applied:

```powershell
# From project root
docker-compose exec api alembic upgrade head

# Or directly
alembic upgrade head
```

New tables created:
- `watchtower_items` - Live feed items from FDA
- `watchtower_sync_status` - Sync status per source

---

## Troubleshooting

### Feed Sync Fails

1. Check network connectivity to FDA RSS:
   ```powershell
   Invoke-WebRequest -Uri "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/drug-recalls/rss.xml" -Method HEAD
   ```

2. Check API logs:
   ```powershell
   docker-compose logs api | Select-String "FDA"
   ```

3. Verify Redis is running:
   ```powershell
   docker-compose exec redis redis-cli ping
   # Expected: PONG
   ```

### EPCIS Parse Fails

1. Verify file encoding is UTF-8
2. Check XML namespace declarations
3. Review API logs for parse errors

### Session Expired

1. Frontend should redirect to `/login`
2. User can re-authenticate
3. Token refresh endpoint available at `/api/auth/refresh`

---

## Expected Outputs

### Successful Feed Sync

```json
{
  "status": "complete",
  "results": [
    {
      "source": "fda_recalls",
      "success": true,
      "items_fetched": 20,
      "items_new": 15,
      "cached": false
    }
  ]
}
```

### Valid EPCIS Upload

```json
{
  "id": 1,
  "filename": "valid.json",
  "validation_status": "valid",
  "event_count": 5,
  "chain_break_count": 0,
  "issues": [
    {
      "type": "missing_field",
      "severity": "low",
      "message": "Disposition is recommended for supply chain visibility"
    }
  ],
  "events": [
    {
      "event_type": "ObjectEvent",
      "action": "ADD",
      "epc_list": ["urn:epc:id:sgtin:..."]
    }
  ]
}
```

### Feed Summary

```json
{
  "total_items": 42,
  "by_source": { "fda_recalls": 42 },
  "last_sync_at": "2026-01-09T18:30:00Z",
  "all_sources_healthy": true,
  "sources_count": 1,
  "total_vendors": 5,
  "high_risk_vendors": 1,
  "active_alerts": 3
}
```
