Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Stop-ByCommandPattern {
    param(
        [Parameter(Mandatory = $true)][string]$Pattern,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $matches = Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $Pattern }

    if (-not $matches) {
        Write-Host "${Label}: no matching process found."
        return
    }

    foreach ($proc in $matches) {
        try {
            Stop-Process -Id $proc.ProcessId -Force
            Write-Host "${Label}: stopped PID $($proc.ProcessId)"
        }
        catch {
            Write-Warning "${Label}: failed to stop PID $($proc.ProcessId): $($_.Exception.Message)"
        }
    }
}

Write-Host "Stopping local dev services..."
Stop-ByCommandPattern -Label "Webhook API" -Pattern "uvicorn\s+webhook_api:app"
Stop-ByCommandPattern -Label "Streamlit App" -Pattern "streamlit\s+run\s+app\.py"
Stop-ByCommandPattern -Label "Stripe Listener" -Pattern "stripe\s+listen\s+--forward-to\s+localhost:8000/stripe/webhook"
Write-Host "Done."
