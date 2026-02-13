# EPCIS Sample Files

This directory contains sample EPCIS files for testing the DSCSA/EPCIS validation functionality in PharmaForge OS.

## Files

### 1. valid.json (JSON - EPCIS 2.0 format)
A complete supply chain scenario in JSON format containing:
- ObjectEvent: Commissioning (ADD)
- ObjectEvent: Packing (OBSERVE)
- AggregationEvent: Case packing (ADD)
- ObjectEvent: Shipping (OBSERVE)
- ObjectEvent: Receiving (OBSERVE)

**Expected Result:** VALID - All required fields present, proper EPC format

### 2. object_event.xml (XML - EPCIS 1.2 format)
ObjectEvent examples demonstrating:
- Product commissioning into the supply chain
- Packing operations
- Shipping with source/destination

**Expected Result:** VALID - Proper XML structure with full epcList

### 3. aggregation_event.xml (XML - EPCIS 1.2 format)
AggregationEvent examples demonstrating:
- Packing units into cases (parentID with childEPCs)
- Packing cases into pallets
- Unpacking at receiving location

**Expected Result:** VALID - Proper parent-child relationships

### 4. broken.json (JSON - Invalid)
Intentionally malformed file for testing error detection:
- Missing eventTime on some events
- Invalid EPC format
- Missing required action field

**Expected Result:** INVALID - Multiple validation errors detected

---

## How to Upload & Test

### Via UI
1. Navigate to **DSCSA / EPCIS** page
2. Click **Upload File**
3. Select any sample file
4. View the **Validation Details** panel for:
   - Status (VALID/INVALID/CHAIN_BREAK)
   - Event count
   - Issue list with severity
   - Parsed events table

### Via API (PowerShell)

```powershell
# 1. Login and get token
$loginBody = @{ email = "admin@acmepharma.com"; password = "YourAdminPassword" } | ConvertTo-Json
$loginResp = Invoke-RestMethod -Uri "http://localhost:8001/api/auth/login" -Method POST -Body $loginBody -ContentType "application/json"
$token = $loginResp.access_token

# 2. Upload EPCIS file
$headers = @{ Authorization = "Bearer $token" }
$filePath = ".\samples\epcis\valid.json"
$response = curl.exe -X POST "http://localhost:8001/api/dscsa/epcis/upload" `
  -H "Authorization: Bearer $token" `
  -F "file=@$filePath"
$response | ConvertFrom-Json | ConvertTo-Json -Depth 5

# 3. List uploads
Invoke-RestMethod -Uri "http://localhost:8001/api/dscsa/epcis/uploads" -Headers $headers

# 4. Get upload details (replace 1 with actual ID)
Invoke-RestMethod -Uri "http://localhost:8001/api/dscsa/epcis/uploads/1" -Headers $headers
```

### Via cURL

```bash
# Upload
curl -X POST http://localhost:8001/api/dscsa/epcis/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@samples/epcis/valid.json"

# List
curl -X GET http://localhost:8001/api/dscsa/epcis/uploads \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Expected Validation Output

### Valid File
```json
{
  "validation_status": "valid",
  "event_count": 5,
  "chain_break_count": 0,
  "issues": [
    {
      "type": "missing_field",
      "severity": "low",
      "message": "Disposition is recommended for supply chain visibility"
    }
  ]
}
```

### Invalid File
```json
{
  "validation_status": "invalid",
  "event_count": 2,
  "chain_break_count": 0,
  "issues": [
    {
      "type": "missing_field",
      "severity": "high",
      "message": "Event time is required for DSCSA compliance"
    },
    {
      "type": "missing_field",
      "severity": "critical",
      "message": "At least one EPC or quantity element is required"
    }
  ]
}
```

---

## EPCIS Standards Reference

- **EPCIS 1.2:** GS1 standard for event-based track and trace
- **EPCIS 2.0:** JSON-LD support, improved semantics
- **CBV (Core Business Vocabulary):** Standardized URIs for bizStep, disposition, etc.
- **DSCSA:** FDA Drug Supply Chain Security Act requirements

### Common bizStep Values
- `urn:epcglobal:cbv:bizstep:commissioning` - Product enters supply chain
- `urn:epcglobal:cbv:bizstep:packing` - Products packed into containers
- `urn:epcglobal:cbv:bizstep:shipping` - Products leave facility
- `urn:epcglobal:cbv:bizstep:receiving` - Products arrive at facility
- `urn:epcglobal:cbv:bizstep:unpacking` - Containers unpacked

### Common disposition Values
- `urn:epcglobal:cbv:disp:active` - Active in inventory
- `urn:epcglobal:cbv:disp:in_progress` - Operation in progress
- `urn:epcglobal:cbv:disp:in_transit` - In transit between locations
