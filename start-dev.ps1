param(
    [switch]$NoStripe
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$envFile = Join-Path $projectRoot "dev.env.ps1"
$envTemplateFile = Join-Path $projectRoot "dev.env.ps1.example"

if (-not (Test-Path $envFile) -and (Test-Path $envTemplateFile)) {
    Copy-Item -Path $envTemplateFile -Destination $envFile
    Write-Warning "Created dev.env.ps1 from template. Fill in real Stripe values."
}

if (Test-Path $envFile) {
    . $envFile
}

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Test-Command -Name $Name)) {
        throw "Missing command '$Name'. Install it first or make sure it is available on PATH."
    }
}

function Get-EnvVarValue {
    param([Parameter(Mandatory = $true)][string]$Name)
    return [Environment]::GetEnvironmentVariable($Name, "Process")
}

function Set-EnvVarValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

function Prompt-ForEnvVar {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Prompt,
        [string]$DefaultValue = ""
    )
    $current = Get-EnvVarValue -Name $Name
    if (-not [string]::IsNullOrWhiteSpace($current)) {
        return $current
    }

    if ($DefaultValue) {
        $inputValue = Read-Host "$Prompt [$DefaultValue]"
        if ([string]::IsNullOrWhiteSpace($inputValue)) {
            $inputValue = $DefaultValue
        }
    }
    else {
        $inputValue = Read-Host $Prompt
    }

    if ([string]::IsNullOrWhiteSpace($inputValue)) {
        throw "Missing required value for '$Name'."
    }

    Set-EnvVarValue -Name $Name -Value $inputValue
    return $inputValue
}

function Save-DevEnvFile {
    param([Parameter(Mandatory = $true)][hashtable]$Vars)
    $lines = @()
    foreach ($name in $Vars.Keys) {
        $value = [string]$Vars[$name]
        $escaped = $value.Replace("'", "''")
        $lines += "`$env:$name = '$escaped'"
    }
    Set-Content -Path $envFile -Value ($lines -join [Environment]::NewLine) -Encoding UTF8
}

function Start-DevWindow {
    param(
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$Command
    )

    $fullCommand = @"
`$Host.UI.RawUI.WindowTitle = '$Title'
Set-Location '$projectRoot'
$Command
"@

    Start-Process powershell -ArgumentList @("-NoExit", "-Command", $fullCommand) | Out-Null
}

Write-Host "Checking prerequisites..."
Assert-Command "python"
Assert-Command "streamlit"
Assert-Command "uvicorn"

$stripeAvailable = Test-Command "stripe"
if (-not $NoStripe -and -not $stripeAvailable) {
    Write-Warning "Stripe CLI is not installed. Skipping stripe listener window."
    Write-Warning "Install with: winget install Stripe.StripeCLI"
}

Write-Host "Bootstrapping Stripe settings (one-time)..."
$databaseUrl = Prompt-ForEnvVar -Name "DATABASE_URL" -Prompt "Enter database URL" -DefaultValue "sqlite:///app.sqlite3"
$supabaseUrl = Prompt-ForEnvVar -Name "SUPABASE_URL" -Prompt "Enter Supabase URL (https://...)"
$supabaseAnonKey = Prompt-ForEnvVar -Name "SUPABASE_ANON_KEY" -Prompt "Enter Supabase anon key"
$stripeSecretKey = Prompt-ForEnvVar -Name "STRIPE_SECRET_KEY" -Prompt "Enter Stripe secret key (sk_test...)" 
$stripePriceId = Prompt-ForEnvVar -Name "STRIPE_PRICE_ID" -Prompt "Enter Stripe price id (price_...)"
$successUrl = Prompt-ForEnvVar -Name "STRIPE_SUCCESS_URL" -Prompt "Enter Stripe success URL" -DefaultValue "http://localhost:8501"
$cancelUrl = Prompt-ForEnvVar -Name "STRIPE_CANCEL_URL" -Prompt "Enter Stripe cancel URL" -DefaultValue "http://localhost:8501"
$webhookSecret = Prompt-ForEnvVar -Name "STRIPE_WEBHOOK_SECRET" -Prompt "Enter Stripe webhook signing secret (whsec_...)"

Save-DevEnvFile -Vars @{
    DATABASE_URL = $databaseUrl
    SUPABASE_URL = $supabaseUrl
    SUPABASE_ANON_KEY = $supabaseAnonKey
    STRIPE_SECRET_KEY = $stripeSecretKey
    STRIPE_PRICE_ID = $stripePriceId
    STRIPE_SUCCESS_URL = $successUrl
    STRIPE_CANCEL_URL = $cancelUrl
    STRIPE_WEBHOOK_SECRET = $webhookSecret
    MAX_UPLOAD_MB = "10"
    MAX_UPLOAD_ROWS = "250000"
    MAX_UPLOAD_COLUMNS = "200"
    MAX_WEBHOOK_BODY_KB = "256"
}
Write-Host "Saved settings to dev.env.ps1"

Write-Host "Starting webhook API..."
Start-DevWindow -Title "Webhook API" -Command "uvicorn webhook_api:app --host 0.0.0.0 --port 8000"

Write-Host "Starting Streamlit app..."
Start-DevWindow -Title "Streamlit App" -Command "streamlit run app.py"

if (-not $NoStripe -and $stripeAvailable) {
    Write-Host "Starting Stripe listener..."
    Start-DevWindow -Title "Stripe Listener" -Command "stripe listen --forward-to localhost:8000/stripe/webhook"
}

Write-Host ""
Write-Host "Dev stack started."
Write-Host "Webhook API:    http://localhost:8000/health"
Write-Host "Streamlit app:  http://localhost:8501"
