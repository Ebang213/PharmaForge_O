<#
.SYNOPSIS
    PharmaForge OS Verification Script for Watchtower and DSCSA functionality.
.DESCRIPTION
    This script tests the Watchtower live feed and DSCSA/EPCIS endpoints.
    Requires a running PharmaForge stack and valid admin credentials.
.PARAMETER BaseUrl
    Base URL for the API (default: http://localhost:8001)
.PARAMETER Credential
    Admin credentials for authentication. If not provided, you will be prompted.
#>
param(
    [string]$BaseUrl = "http://localhost:8001",
    [PSCredential]$Credential
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PharmaForge OS Verification Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if credentials were provided, otherwise prompt securely
if ($null -eq $Credential) {
    Write-Host "Credentials required for authentication." -ForegroundColor Yellow
    $Credential = Get-Credential -UserName "admin@acmepharma.com" -Message "Enter PharmaForge Admin Credentials"
}

$Email = $Credential.UserName

# 1. Login to get token
Write-Host "[1/7] Logging in as $Email..." -ForegroundColor Yellow

# Use the credentials for the API call
$loginBody = @{ 
    email    = $Email
    password = $Credential.GetNetworkCredential().Password 
} | ConvertTo-Json
try {
    $loginResp = Invoke-RestMethod -Uri "$BaseUrl/api/auth/login" -Method POST -Body $loginBody -ContentType "application/json"
    $token = $loginResp.access_token
    Write-Host "  ✓ Login successful" -ForegroundColor Green
}
catch {
    Write-Host "  ✗ Login failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    # Credentials are held in the $Credential object securely
}

$headers = @{ Authorization = "Bearer $token" }

# 2. Test /api/watchtower/sources
Write-Host "[2/7] Testing GET /api/watchtower/sources..." -ForegroundColor Yellow
try {
    $sources = Invoke-RestMethod -Uri "$BaseUrl/api/watchtower/sources" -Headers $headers
    Write-Host "  ✓ Sources endpoint working" -ForegroundColor Green
    Write-Host "    Sources found: $($sources.Count)" -ForegroundColor Gray
    foreach ($src in $sources) {
        $status = if ($src.last_success_at) { "✓" } else { "○" }
        Write-Host "    $status $($src.source_name) ($($src.source_id))" -ForegroundColor Gray
    }
}
catch {
    Write-Host "  ✗ Sources endpoint failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 3. Test /api/watchtower/feed
Write-Host "[3/7] Testing GET /api/watchtower/feed..." -ForegroundColor Yellow
try {
    $feed = Invoke-RestMethod -Uri "$BaseUrl/api/watchtower/feed?limit=10" -Headers $headers
    Write-Host "  ✓ Feed endpoint working" -ForegroundColor Green
    Write-Host "    Items returned: $($feed.Count)" -ForegroundColor Gray
    if ($feed.Count -gt 0) {
        Write-Host "    Latest item: $($feed[0].title.Substring(0, [Math]::Min(60, $feed[0].title.Length)))..." -ForegroundColor Gray
    }
}
catch {
    Write-Host "  ✗ Feed endpoint failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 4. Test /api/watchtower/feed/summary
Write-Host "[4/7] Testing GET /api/watchtower/feed/summary..." -ForegroundColor Yellow
try {
    $summary = Invoke-RestMethod -Uri "$BaseUrl/api/watchtower/feed/summary" -Headers $headers
    Write-Host "  ✓ Summary endpoint working" -ForegroundColor Green
    Write-Host "    Total feed items: $($summary.total_items)" -ForegroundColor Gray
    Write-Host "    Total vendors: $($summary.total_vendors)" -ForegroundColor Gray
    Write-Host "    Active alerts: $($summary.active_alerts)" -ForegroundColor Gray
    Write-Host "    All sources healthy: $($summary.all_sources_healthy)" -ForegroundColor Gray
}
catch {
    Write-Host "  ✗ Summary endpoint failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 5. Test EPCIS upload
Write-Host "[5/7] Testing EPCIS upload..." -ForegroundColor Yellow
$sampleFile = "$PSScriptRoot\..\samples\epcis\valid.json"
if (Test-Path $sampleFile) {
    try {
        # Use curl for multipart form upload
        $uploadResult = & curl.exe -s -X POST "$BaseUrl/api/dscsa/epcis/upload" `
            -H "Authorization: Bearer $token" `
            -F "file=@$sampleFile"
        $uploadData = $uploadResult | ConvertFrom-Json
        Write-Host "  ✓ EPCIS upload successful" -ForegroundColor Green
        Write-Host "    Upload ID: $($uploadData.id)" -ForegroundColor Gray
        Write-Host "    Status: $($uploadData.validation_status)" -ForegroundColor Gray
        Write-Host "    Events: $($uploadData.event_count)" -ForegroundColor Gray
        $uploadId = $uploadData.id
    }
    catch {
        Write-Host "  ✗ EPCIS upload failed: $($_.Exception.Message)" -ForegroundColor Red
        $uploadId = $null
    }
}
else {
    Write-Host "  ⚠ Sample file not found: $sampleFile" -ForegroundColor Yellow
    $uploadId = $null
}

# 6. Test EPCIS list
Write-Host "[6/7] Testing GET /api/dscsa/epcis/uploads..." -ForegroundColor Yellow
try {
    $uploads = Invoke-RestMethod -Uri "$BaseUrl/api/dscsa/epcis/uploads" -Headers $headers
    Write-Host "  ✓ EPCIS list endpoint working" -ForegroundColor Green
    Write-Host "    Uploads found: $($uploads.Count)" -ForegroundColor Gray
}
catch {
    Write-Host "  ✗ EPCIS list endpoint failed: $($_.Exception.Message)" -ForegroundColor Red
}

# 7. Test EPCIS detail (if we have an upload ID)
Write-Host "[7/7] Testing GET /api/dscsa/epcis/uploads/{id}..." -ForegroundColor Yellow
if ($uploadId) {
    try {
        $detail = Invoke-RestMethod -Uri "$BaseUrl/api/dscsa/epcis/uploads/$uploadId" -Headers $headers
        Write-Host "  ✓ EPCIS detail endpoint working" -ForegroundColor Green
        Write-Host "    File: $($detail.filename)" -ForegroundColor Gray
        Write-Host "    Status: $($detail.validation_status)" -ForegroundColor Gray
        Write-Host "    Events: $($detail.event_count), Issues: $(($detail.issues).Count)" -ForegroundColor Gray
    }
    catch {
        Write-Host "  ✗ EPCIS detail endpoint failed: $($_.Exception.Message)" -ForegroundColor Red
    }
}
elseif ($uploads.Count -gt 0) {
    try {
        $testId = $uploads[0].id
        $detail = Invoke-RestMethod -Uri "$BaseUrl/api/dscsa/epcis/uploads/$testId" -Headers $headers
        Write-Host "  ✓ EPCIS detail endpoint working (used existing upload)" -ForegroundColor Green
    }
    catch {
        Write-Host "  ✗ EPCIS detail endpoint failed: $($_.Exception.Message)" -ForegroundColor Red
    }
}
else {
    Write-Host "  ⚠ Skipped - no uploads available" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Verification Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Manual tests to perform:" -ForegroundColor Yellow
Write-Host "  1. Open http://localhost (browser) and log in" -ForegroundColor Gray
Write-Host "  2. Navigate to Watchtower - should see Feed Sources section" -ForegroundColor Gray
Write-Host "  3. Click 'Sync Now' - should populate FDA recalls feed" -ForegroundColor Gray
Write-Host "  4. Navigate to DSCSA - upload a sample EPCIS file" -ForegroundColor Gray
Write-Host "  5. Check validation report shows events and issues" -ForegroundColor Gray
Write-Host ""
