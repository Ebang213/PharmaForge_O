<#
.SYNOPSIS
    PharmaForge OS - Risk Intelligence Loop End-to-End Verification Script
.DESCRIPTION
    This script tests the complete Risk Intelligence Loop workflow:
    1. Login
    2. Upload Evidence
    3. Run Risk Findings
    4. Export Audit Packet
    
    This is NOT a demo - it requires a running API and will FAIL LOUDLY if any step fails.
    No mock data, no fallbacks, no pretend success states.

.PARAMETER BaseUrl
    Base URL for the API (default: http://localhost:8001)
.PARAMETER Credential
    Admin credentials for authentication. If not provided, you will be prompted.
#>
param(
    [string]$BaseUrl = "http://localhost:8001",
    [PSCredential]$Credential
)

$ErrorActionPreference = "Stop"
$script:FailedSteps = @()

function Write-Step {
    param([string]$StepNum, [string]$Message, [ConsoleColor]$Color = "Yellow")
    Write-Host "[$StepNum] $Message" -ForegroundColor $Color
}

function Write-Success {
    param([string]$Message)
    Write-Host "  ✓ $Message" -ForegroundColor Green
}

function Write-Failure {
    param([string]$Message)
    Write-Host "  ✗ $Message" -ForegroundColor Red
    $script:FailedSteps += $Message
}

function Write-Detail {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor Gray
}

Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   PharmaForge OS - Risk Intelligence Loop Verification         ║" -ForegroundColor Cyan
Write-Host "║   NO MOCK DATA - REAL API CALLS ONLY - FAILS LOUDLY            ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "Target: $BaseUrl" -ForegroundColor White
Write-Host ""

# Check if credentials were provided, otherwise prompt securely
if ($null -eq $Credential) {
    Write-Host "Credentials required for authentication." -ForegroundColor Yellow
    $Credential = Get-Credential -Message "Enter PharmaForge Admin Credentials"
}

$Email = $Credential.UserName
$Password = $Credential.GetNetworkCredential().Password

# ============================================================================
# STEP 1: API Health Check
# ============================================================================
Write-Step "1/6" "Testing API Health at /api/health..."
try {
    $healthResp = Invoke-RestMethod -Uri "$BaseUrl/api/health" -Method GET -ContentType "application/json"
    Write-Success "API is healthy"
    Write-Detail "Status: $($healthResp.status), Version: $($healthResp.version)"
}
catch {
    Write-Failure "API health check failed: $($_.Exception.Message)"
    Write-Host ""
    Write-Host "FATAL: API is not reachable. Cannot continue." -ForegroundColor Red
    exit 1
}

# ============================================================================
# STEP 2: Login
# ============================================================================
Write-Step "2/6" "Logging in as $Email..."
$loginBody = @{ 
    email    = $Email
    password = $Password
} | ConvertTo-Json

try {
    $loginResp = Invoke-RestMethod -Uri "$BaseUrl/api/auth/login" -Method POST -Body $loginBody -ContentType "application/json"
    $token = $loginResp.access_token
    if (-not $token) {
        throw "No access_token in response"
    }
    Write-Success "Login successful"
    Write-Detail "User: $($loginResp.user.full_name) (Role: $($loginResp.user.role))"
    Write-Detail "Token: $($token.Substring(0, [Math]::Min(20, $token.Length)))..."
}
catch {
    Write-Failure "Login failed: $($_.Exception.Message)"
    Write-Host ""
    Write-Host "FATAL: Cannot authenticate. Cannot continue." -ForegroundColor Red
    exit 1
}

$headers = @{ Authorization = "Bearer $token" }

# ============================================================================
# STEP 3: Upload Evidence
# ============================================================================
Write-Step "3/6" "Uploading test evidence file..."

# Create a temporary test file
$testContent = @"
PharmaForge OS Test Evidence Document
Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

This document is used to verify the Risk Intelligence Loop.

Keywords for finding extraction:
- Temperature monitoring is critical for cold chain storage
- cGMP manufacturing requirements must be validated
- Supplier qualification audits are pending
- DSCSA serialization compliance check required
- Labeling verification needed for batch 2024-0042

Vendor: Acme Pharma Labs Inc.
Product: Test Drug XYZ
Batch: 2024-0042
"@

$tempFile = [System.IO.Path]::GetTempFileName() -replace '\.tmp$', '.txt'
$testContent | Out-File -FilePath $tempFile -Encoding UTF8

try {
    # Use curl for multipart upload
    $uploadResult = & curl.exe -s -X POST "$BaseUrl/api/evidence" `
        -H "Authorization: Bearer $token" `
        -F "file=@$tempFile"
    
    if ($LASTEXITCODE -ne 0) {
        throw "curl returned exit code $LASTEXITCODE"
    }
    
    $uploadData = $uploadResult | ConvertFrom-Json
    if (-not $uploadData.id) {
        throw "No evidence ID in response: $uploadResult"
    }
    
    $evidenceId = $uploadData.id
    Write-Success "Evidence uploaded successfully"
    Write-Detail "Evidence ID: $evidenceId"
    Write-Detail "Filename: $($uploadData.filename)"
    Write-Detail "SHA256: $($uploadData.sha256.Substring(0, 16))..."
}
catch {
    Write-Failure "Evidence upload failed: $($_.Exception.Message)"
    $evidenceId = $null
}
finally {
    # Clean up temp file
    if (Test-Path $tempFile) {
        Remove-Item $tempFile -Force
    }
}

if (-not $evidenceId) {
    Write-Host ""
    Write-Host "FATAL: Evidence upload failed. Cannot continue with Risk Intelligence Loop." -ForegroundColor Red
    exit 1
}

# ============================================================================
# STEP 4: Run Risk Findings
# ============================================================================
Write-Step "4/6" "Running risk findings extraction on evidence $evidenceId..."

try {
    $findingsResp = Invoke-RestMethod -Uri "$BaseUrl/api/risk/findings/run?evidence_id=$evidenceId" -Method POST -Headers $headers
    if (-not $findingsResp.findings -or $findingsResp.findings.Count -eq 0) {
        throw "No findings generated"
    }
    
    Write-Success "Risk findings extracted successfully"
    Write-Detail "Found: $($findingsResp.findings.Count) finding(s)"
    Write-Detail "Message: $($findingsResp.message)"
    
    foreach ($finding in $findingsResp.findings) {
        Write-Detail "  [$($finding.severity)] $($finding.title)"
    }
}
catch {
    Write-Failure "Risk findings extraction failed: $($_.Exception.Message)"
}

# ============================================================================
# STEP 5: Get Stored Findings
# ============================================================================
Write-Step "5/6" "Retrieving stored findings for evidence $evidenceId..."

try {
    $storedFindings = Invoke-RestMethod -Uri "$BaseUrl/api/risk/findings?evidence_id=$evidenceId" -Method GET -Headers $headers
    if ($storedFindings.Count -eq 0) {
        throw "No stored findings returned"
    }
    
    Write-Success "Stored findings retrieved"
    Write-Detail "Total findings: $($storedFindings.Count)"
}
catch {
    Write-Failure "Failed to retrieve stored findings: $($_.Exception.Message)"
}

# ============================================================================
# STEP 6: Export Audit Packet
# ============================================================================
Write-Step "6/6" "Exporting audit packet for evidence $evidenceId..."

try {
    $packetResp = Invoke-RestMethod -Uri "$BaseUrl/api/risk/export-packet/$evidenceId" -Method GET -Headers $headers
    if (-not $packetResp.content) {
        throw "No content in audit packet"
    }
    
    Write-Success "Audit packet exported successfully"
    Write-Detail "Filename: $($packetResp.filename)"
    Write-Detail "Content-Type: $($packetResp.content_type)"
    Write-Detail "Content Length: $($packetResp.content.Length) characters"
    
    # Show first few lines of the packet
    $lines = $packetResp.content -split "`n" | Select-Object -First 5
    foreach ($line in $lines) {
        Write-Detail "  $line"
    }
}
catch {
    Write-Failure "Audit packet export failed: $($_.Exception.Message)"
}

# ============================================================================
# SUMMARY
# ============================================================================
Write-Host ""
Write-Host "╔════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                       VERIFICATION SUMMARY                      ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

if ($script:FailedSteps.Count -eq 0) {
    Write-Host "  ✓ ALL STEPS PASSED" -ForegroundColor Green
    Write-Host ""
    Write-Host "  The Risk Intelligence Loop is fully operational:" -ForegroundColor White
    Write-Host "    1. API Health Check     - OK" -ForegroundColor Green
    Write-Host "    2. Authentication       - OK" -ForegroundColor Green
    Write-Host "    3. Evidence Upload      - OK" -ForegroundColor Green
    Write-Host "    4. Findings Extraction  - OK" -ForegroundColor Green
    Write-Host "    5. Findings Retrieval   - OK" -ForegroundColor Green
    Write-Host "    6. Audit Packet Export  - OK" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Evidence ID: $evidenceId" -ForegroundColor White
    Write-Host ""
    exit 0
}
else {
    Write-Host "  ✗ SOME STEPS FAILED" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Failed steps:" -ForegroundColor Red
    foreach ($failure in $script:FailedSteps) {
        Write-Host "    - $failure" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "  The Risk Intelligence Loop is NOT fully operational." -ForegroundColor Red
    Write-Host "  Fix the above issues and re-run this verification script." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}
