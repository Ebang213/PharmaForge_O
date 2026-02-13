<#
.SYNOPSIS
    Watchtower verification script for PharmaForge OS.
.DESCRIPTION
    Logs in, triggers Watchtower sync, fetches feed and summary,
    uploads a sample PDF evidence file, and lists evidence items.
    
    DONE GATE: This script verifies:
    - Sync returns HTTP 200 (not 500)
    - Per-source results are printed
    - Fails if ALL sources fail
.PARAMETER BaseUrl
    Base URL for the API (default: http://localhost:8001)
.PARAMETER Credential
    Admin credentials for authentication. If not provided, you will be prompted.
#>
param(
    [string]$BaseUrl = "http://localhost:8001",
    [PSCredential]$Credential
)

function Write-StepResult {
    param(
        [string]$Label,
        [bool]$Ok,
        [string]$Detail = ""
    )
    if ($Ok) {
        Write-Host "[PASS] $Label" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] $Label" -ForegroundColor Red
    }
    if ($Detail) {
        Write-Host "       $Detail" -ForegroundColor Gray
    }
}

function New-SamplePdf {
    param([string]$Path)
    $nl = "`n"
    $stream = "BT${nl}/F1 12 Tf${nl}72 72 Td${nl}(Watchtower Evidence Sample) Tj${nl}ET${nl}"
    $streamBytes = [System.Text.Encoding]::ASCII.GetBytes($stream)

    $objects = @()
    $objects += "1 0 obj${nl}<< /Type /Catalog /Pages 2 0 R >>${nl}endobj${nl}"
    $objects += "2 0 obj${nl}<< /Type /Pages /Kids [3 0 R] /Count 1 >>${nl}endobj${nl}"
    $objects += "3 0 obj${nl}<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>${nl}endobj${nl}"
    $objects += "4 0 obj${nl}<< /Length $($streamBytes.Length) >>${nl}stream${nl}$stream" + "endstream${nl}endobj${nl}"
    $objects += "5 0 obj${nl}<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>${nl}endobj${nl}"

    $header = "%PDF-1.4${nl}"
    $body = ($objects -join "")

    $headerBytes = [System.Text.Encoding]::ASCII.GetBytes($header)
    $bodyBytes = [System.Text.Encoding]::ASCII.GetBytes($body)

    $offsets = @()
    $offset = $headerBytes.Length
    foreach ($obj in $objects) {
        $objBytes = [System.Text.Encoding]::ASCII.GetBytes($obj)
        $offsets += $offset
        $offset += $objBytes.Length
    }

    $xref = "xref${nl}0 $($objects.Count + 1)${nl}"
    $xref += "0000000000 65535 f ${nl}"
    foreach ($objOffset in $offsets) {
        $xref += ("{0:0000000000} 00000 n ${nl}" -f $objOffset)
    }

    $xrefBytes = [System.Text.Encoding]::ASCII.GetBytes($xref)
    $startxref = $headerBytes.Length + $bodyBytes.Length + $xrefBytes.Length
    $trailer = "trailer${nl}<< /Size $($objects.Count + 1) /Root 1 0 R >>${nl}startxref${nl}$startxref${nl}%%EOF${nl}"

    $pdf = $header + $body + $xref + $trailer
    [System.IO.File]::WriteAllBytes($Path, [System.Text.Encoding]::ASCII.GetBytes($pdf))
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Watchtower Verification Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if ($null -eq $Credential) {
    Write-Host "Credentials required for authentication." -ForegroundColor Yellow
    $Credential = Get-Credential -UserName "admin@acmepharma.com" -Message "Enter PharmaForge Admin Credentials"
}

$email = $Credential.UserName
$password = $Credential.GetNetworkCredential().Password

$overallPass = $true

Write-Host "[1/6] Logging in..." -ForegroundColor Yellow
$loginBody = @{ email = $email; password = $password } | ConvertTo-Json
try {
    $loginResp = Invoke-RestMethod -Uri "$BaseUrl/api/auth/login" -Method POST -Body $loginBody -ContentType "application/json"
    $token = $loginResp.access_token
    Write-StepResult "Login" ($null -ne $token) "User: $email"
} catch {
    Write-StepResult "Login" $false $_.Exception.Message
    exit 1
}

$headers = @{ Authorization = "Bearer $token" }

Write-Host "[2/6] Triggering Watchtower sync?force=true..." -ForegroundColor Yellow
$syncPass = $false
try {
    # Use WebRequest to check status code directly
    $syncResponse = Invoke-WebRequest -Uri "$BaseUrl/api/watchtower/sync?force=true" -Method POST -Headers $headers -UseBasicParsing
    $syncStatusCode = $syncResponse.StatusCode
    
    if ($syncStatusCode -eq 200) {
        $syncResp = $syncResponse.Content | ConvertFrom-Json
        $syncPass = $true
        
        # Per-source status
        $isDegraded = $syncResp.degraded -eq $true
        $sourcesSucceeded = $syncResp.sources_succeeded
        $sourcesFailed = $syncResp.sources_failed
        $itemsAdded = $syncResp.total_items_added
        
        if ($isDegraded) {
            Write-Host "[PASS] Sync (HTTP 200 - DEGRADED MODE)" -ForegroundColor Yellow
            Write-Host "       WARNING: Some sources failed but sync completed" -ForegroundColor Yellow
        } else {
            Write-StepResult "Sync" $true "HTTP 200, Status: $($syncResp.status)"
        }
        
        # Print per-source results table
        Write-Host ""
        Write-Host "       Per-Source Results:" -ForegroundColor Cyan
        Write-Host "       +-----------------------+--------+--------+----------+----------+" -ForegroundColor Gray
        Write-Host "       | Source                | OK     | HTTP   | Fetched  | Saved    |" -ForegroundColor Gray
        Write-Host "       +-----------------------+--------+--------+----------+----------+" -ForegroundColor Gray
        
        if ($syncResp.results) {
            foreach ($result in $syncResp.results) {
                $srcName = $result.source.PadRight(21)
                $ok = if ($result.success) { "Yes".PadRight(6) } else { "No".PadRight(6) }
                $http = if ($null -ne $result.last_http_status) { 
                    $result.last_http_status.ToString().PadRight(6) 
                } else { 
                    "-".PadRight(6) 
                }
                $fetched = if ($null -ne $result.items_fetched) { 
                    $result.items_fetched.ToString().PadRight(8) 
                } else { 
                    "0".PadRight(8) 
                }
                $saved = if ($null -ne $result.items_added) { 
                    $result.items_added.ToString().PadRight(8) 
                } elseif ($null -ne $result.items_saved) { 
                    $result.items_saved.ToString().PadRight(8) 
                } else { 
                    "0".PadRight(8) 
                }
                
                $rowColor = if ($result.success) { "Green" } else { "Red" }
                Write-Host "       | $srcName | $ok | $http | $fetched | $saved |" -ForegroundColor $rowColor
                
                # Print error if failed
                if (-not $result.success -and $result.error_message) {
                    $errMsg = $result.error_message
                    if ($errMsg.Length -gt 60) { $errMsg = $errMsg.Substring(0, 60) + "..." }
                    Write-Host "       |   Error: $errMsg" -ForegroundColor Red
                }
            }
        }
        Write-Host "       +-----------------------+--------+--------+----------+----------+" -ForegroundColor Gray
        Write-Host ""
        
        # DONE GATE: Fail if ALL sources failed
        if ($sourcesFailed -gt 0 -and $sourcesSucceeded -eq 0) {
            Write-Host "[FAIL] All sources failed - product is not live" -ForegroundColor Red
            $syncPass = $false
        } else {
            Write-Host "       Summary: $sourcesSucceeded succeeded, $sourcesFailed failed, $itemsAdded items added" -ForegroundColor Cyan
        }
        
    } else {
        Write-StepResult "Sync" $false "HTTP $syncStatusCode (expected 200)"
    }
} catch {
    $errorMsg = $_.Exception.Message
    $statusCode = $null
    if ($_.Exception.Response) {
        $statusCode = [int]$_.Exception.Response.StatusCode
    }
    if ($statusCode) {
        Write-StepResult "Sync" $false "HTTP $statusCode - $errorMsg"
    } else {
        Write-StepResult "Sync" $false $errorMsg
    }
}

if (-not $syncPass) {
    $overallPass = $false
}

Write-Host "[3/6] Fetching feed items..." -ForegroundColor Yellow
try {
    $feed = Invoke-RestMethod -Uri "$BaseUrl/api/watchtower/feed?limit=5" -Headers $headers
    $count = if ($feed) { $feed.Count } else { 0 }
    Write-StepResult "Feed" $true "Items: $count"
} catch {
    Write-StepResult "Feed" $false $_.Exception.Message
    $overallPass = $false
}

Write-Host "[4/6] Fetching summary..." -ForegroundColor Yellow
try {
    $summary = Invoke-RestMethod -Uri "$BaseUrl/api/watchtower/summary" -Headers $headers
    $summaryOk = $null -ne $summary.active_alerts
    Write-StepResult "Summary" $summaryOk "Feed items: $($summary.feed_items)"
} catch {
    Write-StepResult "Summary" $false $_.Exception.Message
    $overallPass = $false
}

Write-Host "[5/6] Uploading evidence..." -ForegroundColor Yellow
$tempPdf = Join-Path $env:TEMP "watchtower_evidence_sample.pdf"
$uploadData = $null
try {
    New-SamplePdf -Path $tempPdf
    $uploadResult = & curl.exe -s -X POST "$BaseUrl/api/watchtower/evidence" `
        -H "Authorization: Bearer $token" `
        -F "file=@$tempPdf"
    $uploadData = $uploadResult | ConvertFrom-Json
    $uploadOk = $null -ne $uploadData.id
    Write-StepResult "Evidence Upload" $uploadOk "ID: $($uploadData.id)"
} catch {
    Write-StepResult "Evidence Upload" $false $_.Exception.Message
}

Write-Host "[6/6] Listing evidence..." -ForegroundColor Yellow
try {
    $evidence = Invoke-RestMethod -Uri "$BaseUrl/api/watchtower/evidence?limit=5" -Headers $headers
    $evidenceCount = if ($evidence) { $evidence.Count } else { 0 }
    Write-StepResult "Evidence List" $true "Items: $evidenceCount"
    if ($uploadData -and $uploadData.id) {
        $uploadedEvidence = @($evidence | Where-Object { $_.id -eq $uploadData.id })
        $hasUpload = $uploadedEvidence.Count -gt 0
        Write-StepResult "Evidence Present" $hasUpload "Uploaded ID: $($uploadData.id)"
    }
} catch {
    Write-StepResult "Evidence List" $false $_.Exception.Message
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
if ($overallPass) {
    Write-Host "DONE GATE: PASSED" -ForegroundColor Green
} else {
    Write-Host "DONE GATE: FAILED" -ForegroundColor Red
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (-not $overallPass) {
    exit 1
}
