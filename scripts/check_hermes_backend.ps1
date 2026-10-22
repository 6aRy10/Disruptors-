# HERMES safe diagnostic for local FastAPI and Vite proxy.
# No DB writes, no migrations, no secrets or raw response bodies.
param(
    [string]$Backend = "http://127.0.0.1:8000",
    [string]$Frontend = "http://127.0.0.1:5173"
)

$ErrorActionPreference = "Stop"

function Probe($Label, $Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 12
        $status = [int]$response.StatusCode
        Write-Host ("{0}: HTTP {1}" -f $Label, $status)
        return @{ OK = $true; Status = $status; Body = $response.Content }
    } catch {
        $code = $null
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $code = [int]$_.Exception.Response.StatusCode
        }
        if ($null -ne $code) {
            Write-Host ("{0}: HTTP {1}" -f $Label, $code) -ForegroundColor Yellow
        } else {
            Write-Host ("{0}: CONNECTION FAILED ({1})" -f $Label, $_.Exception.GetType().Name) -ForegroundColor Red
        }
        return @{ OK = $false; Status = $code }
    }
}

Write-Host "HERMES READ-ONLY BACKEND DIAGNOSTIC" -ForegroundColor Cyan
Write-Host "This does not change PostgreSQL."

$schema = Probe "FastAPI OpenAPI" "$Backend/openapi.json"
if (-not $schema.OK) {
    Write-Host "FastAPI may not be running on port 8000, or another process owns the port."
} else {
    try {
        $openapi = $schema.Body | ConvertFrom-Json
        $hasRoute = $null -ne $openapi.paths.PSObject.Properties["/app-data/readiness"]
        Write-Host ("Latest readiness route present: {0}" -f $hasRoute)
        if (-not $hasRoute) {
            Write-Host "The running backend is older than the active branch, or the wrong app is on port 8000." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "The server returned an unexpected OpenAPI body." -ForegroundColor Yellow
    }
}

$diagnostic = Probe "Backend readiness" "$Backend/app-data/readiness"
if ($diagnostic.OK) {
    try {
        $data = $diagnostic.Body | ConvertFrom-Json
        Write-Host ("Readiness: {0}" -f $data.status)
        Write-Host ("Selected database target: {0}" -f $data.database_selection.selected_target)
        Write-Host ("Local URL configured: {0}; Aiven URL configured: {1}; Explicit target: {2}" -f $data.database_selection.local_url_present, $data.database_selection.aiven_url_present, $data.database_selection.explicit_target)
        Write-Host ("Database: {0}; Network facilities: {1}; Schema: {2}" -f $data.database.status, $data.database.network_facility_count, $data.schema.status)
        if ($data.schema.missing_tables) {
            Write-Host ("Missing tables: {0}" -f ($data.schema.missing_tables -join ", "))
        }
        if ($data.database.error_type) {
            Write-Host ("Connection/configuration error type: {0}" -f $data.database.error_type) -ForegroundColor Yellow
        }
        if ($data.endpoints) {
            foreach ($entry in $data.endpoints.PSObject.Properties) {
                $errorDetail = ""
                if ($entry.Value.error_type) { $errorDetail = " - " + $entry.Value.error_type }
                if ($entry.Value.sqlstate) { $errorDetail += " - SQLSTATE " + $entry.Value.sqlstate }
                Write-Host ("{0}: {1}{2}" -f $entry.Name, $entry.Value.status, $errorDetail)
            }
        }
        Write-Host ("Next step: {0}" -f $data.action)
    } catch {
        Write-Host "Readiness returned an unexpected JSON body." -ForegroundColor Yellow
    }
} else {
    Write-Host "Restart Uvicorn from the latest feat/db-foundation checkout before retrying." -ForegroundColor Yellow
}

Probe "Direct backend health" "$Backend/health" | Out-Null
Probe "Backend incidents" "$Backend/app-data/incidents?limit=1" | Out-Null
Probe "Backend activity" "$Backend/app-data/activity?limit=1" | Out-Null
Probe "Backend facilities" "$Backend/app-data/map/facilities?limit=1" | Out-Null
Probe "Vite proxy readiness" "$Frontend/app-data/readiness" | Out-Null
Write-Host "Diagnostic complete. Do not paste any database URLs or tokens."
