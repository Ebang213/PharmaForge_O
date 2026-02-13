<#
.SYNOPSIS
    Watchtower Feeds verification script for PharmaForge OS.
.DESCRIPTION
    Logs in, triggers Watchtower sync, and prints overall_status + each source
    status + last_error_message. Fails only if sync returns non-200 OR all sources fail.
.PARAMETER BaseUrl
    Base URL for the API (default: http://localhost:8001)
.PARAMETER Credential
    Admin credentials for authentication. If not provided, defaults are used.
.PARAMETER Email
    Admin email (default: admin@acmepharma.com)
.PARAMETER Password
    Admin password (default: pharmaforge123)
.EXAMPLE
    .\verify_watchtower_feeds.ps1 -BaseUrl "http://localhost:8001"
#>
param(
    [string]$BaseUrl = "http://localhost:8001",
    [PSCredential]$Credential,
    [string]$Email = "admin@acmepharma.com",
    [string]$Password = "pharmaforge123"
)

$ErrorActionPreference = "Stop"

function Write-Status {
    param(
        [string]$Label,
        [string]$Status,
        [string]$Detail = ""
    )
    $color = switch ($Status) {
        "ok" { "Green" }
        "healthy" { "Green" }
        "degraded" { "Yellow" }
        "error" { "Red" }
        "pending" { "Gray" }
        default { "White" }
    }
    Write-Host "[$Status] $Label" -ForegroundColor $color
    if ($Detail) {
        Write-Host "        $Detail" -ForegroundColor Gray
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Watchtower Feeds Verification" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Base URL: $BaseUrl" -ForegroundColor Gray
Write-Host ""

# Get credentials
if ($null -ne $Credential) {
    $Email = $Credential.UserName
    $Password = $Credential.GetNetworkCredential().Password
}

# Step 1: Login
Write-Host "[1/3] Logging in as $Email..." -ForegroundColor Yellow
$loginBody = @{ email = $Email; password = $Password } | ConvertTo-Json
try {
    $loginResp = Invoke-RestMethod -Uri "$BaseUrl/api/auth/login" -Method POST -Body $loginBody -ContentType "application/json"
    $token = $loginResp.access_token
    if (-not $token) {
        Write-Host "[FAIL] Login failed - no token received" -ForegroundColor Red
        exit 1
    }
    Write-Host "[PASS] Login successful" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] Login failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

$headers = @{ Authorization = "Bearer $token" }

# Step 2: Trigger sync
Write-Host ""
Write-Host "[2/3] Triggering Watchtower sync (force=true)..." -ForegroundColor Yellow

$syncFailed = $false
$allSourcesFailed = $false
$syncResult = $null

try {
    $syncResp = Invoke-WebRequest -Uri "$BaseUrl/api/watchtower/sync?force=true" -Method POST -Headers $headers -UseBasicParsing
    $syncResult = $syncResp.Content | ConvertFrom-Json

    $httpStatus = $syncResp.StatusCode
    Write-Host "HTTP Status: $httpStatus" -ForegroundColor Gray

    if ($httpStatus -ge 500) {
        Write-Host "[FAIL] Sync returned HTTP $httpStatus (server error)" -ForegroundColor Red
        $syncFailed = $true
    } elseif ($httpStatus -eq 502) {
        Write-Host "[FAIL] Sync returned HTTP 502 (all sources failed)" -ForegroundColor Red
        $syncFailed = $true
        $allSourcesFailed = $true
    }
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Write-Host "[FAIL] Sync request failed: HTTP $statusCode - $($_.Exception.Message)" -ForegroundColor Red

    # Try to parse error response
    try {
        $errorStream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($errorStream)
        $errorBody = $reader.ReadToEnd() | ConvertFrom-Json
        if ($errorBody.results) {
            $syncResult = $errorBody
        }
    } catch {}

    if ($statusCode -eq 502) {
        $allSourcesFailed = $true
    }
    $syncFailed = $true
}

# Step 3: Print results
Write-Host ""
Write-Host "[3/3] Sync Results Summary" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Gray

if ($syncResult) {
    # Overall status
    $overallStatus = $syncResult.status
    $isDegraded = $syncResult.degraded
    $sourcesSucceeded = $syncResult.sources_succeeded
    $sourcesFailed = $syncResult.sources_failed
    $totalItems = $syncResult.total_items_added

    Write-Host ""
    Write-Host "Overall Status:" -ForegroundColor White -NoNewline

    if ($overallStatus -eq "ok" -and -not $isDegraded) {
        Write-Host " HEALTHY" -ForegroundColor Green
    } elseif ($overallStatus -eq "ok" -and $isDegraded) {
        Write-Host " DEGRADED" -ForegroundColor Yellow
    } else {
        Write-Host " ERROR" -ForegroundColor Red
    }

    Write-Host "Sources Succeeded: $sourcesSucceeded" -ForegroundColor Gray
    Write-Host "Sources Failed:    $sourcesFailed" -ForegroundColor Gray
    Write-Host "Items Added:       $totalItems" -ForegroundColor Gray
    Write-Host ""

    # Per-source details
    Write-Host "Per-Source Status:" -ForegroundColor White
    Write-Host "----------------------------------------" -ForegroundColor Gray

    foreach ($result in $syncResult.results) {
        $sourceId = $result.source
        $success = $result.success
        $itemsFetched = $result.items_fetched
        $itemsAdded = $result.items_added
        $errorMsg = $result.error_message
        $httpStatus = $result.last_http_status
        $cached = $result.cached

        if ($success) {
            $status = if ($cached) { "cached" } else { "ok" }
            $detail = "fetched=$itemsFetched, added=$itemsAdded"
            if ($httpStatus) { $detail += ", http=$httpStatus" }
            Write-Status -Label $sourceId -Status $status -Detail $detail
        } else {
            $detail = if ($errorMsg) {
                $errorMsg.Substring(0, [Math]::Min(80, $errorMsg.Length))
            } else {
                "Unknown error"
            }
            if ($httpStatus) { $detail = "http=$httpStatus - $detail" }
            Write-Status -Label $sourceId -Status "error" -Detail $detail
        }
    }
} else {
    Write-Host "No sync result data available" -ForegroundColor Red
}

Write-Host ""
Write-Host "----------------------------------------" -ForegroundColor Gray

# Determine exit code
# Fail only if: sync returns non-200 OR all sources fail
if ($syncFailed -and $allSourcesFailed) {
    Write-Host "[FAIL] All sources failed - exiting with error" -ForegroundColor Red
    exit 1
} elseif ($syncFailed) {
    Write-Host "[FAIL] Sync returned non-200 status" -ForegroundColor Red
    exit 1
} elseif ($syncResult -and $syncResult.sources_succeeded -eq 0 -and $syncResult.sources_failed -gt 0) {
    Write-Host "[FAIL] All sources failed" -ForegroundColor Red
    exit 1
} elseif ($syncResult -and $syncResult.degraded) {
    Write-Host "[WARN] Sync completed but some sources failed (degraded mode)" -ForegroundColor Yellow
    Write-Host "[PASS] Verification passed (degraded is acceptable)" -ForegroundColor Green
    exit 0
} else {
    Write-Host "[PASS] All sources healthy" -ForegroundColor Green
    exit 0
}
