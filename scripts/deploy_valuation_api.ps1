# Deploy del valuation-api a Cloud Run (motor de valoracion, sin LLM).
#
# Patron: pre-copia mcp_servers/ dentro de valuation_api/ (build context),
# despliega desde ahi, y limpia. Igual que deploy_frontend.ps1.
#
# La API key (X-Api-Key) protege /valuate. Se genera una si no se pasa por
# parametro -ApiKey. ANOTA la key que imprime al final: la necesitas en
# Decomind (env var VALUATION_API_URL + la key).
#
# Uso:
#   .\scripts\deploy_valuation_api.ps1
#   .\scripts\deploy_valuation_api.ps1 -ApiKey "mi-clave-fija"

param(
    [string]$ApiKey = ""
)

$ErrorActionPreference = "Stop"

$PROJECT  = "decomind-agent-challenge"
$REGION   = "europe-west1"
$SA_NAME  = "decomind-agent-dev"
$SA_EMAIL = "$SA_NAME@$PROJECT.iam.gserviceaccount.com"
$SERVICE  = "valuation-api"

if (-not $ApiKey) {
    $ApiKey = [guid]::NewGuid().ToString("N")
    Write-Host "Generated API key (SAVE THIS): $ApiKey" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Deploying $SERVICE" -ForegroundColor Cyan
Write-Host ""

# Pre-copia mcp_servers/ al build context
if (Test-Path valuation_api\mcp_servers) { Remove-Item -Recurse -Force valuation_api\mcp_servers }
Write-Host "Copying mcp_servers/ into build context..." -ForegroundColor Yellow
Copy-Item -Recurse -Force mcp_servers valuation_api\mcp_servers
Get-ChildItem -Path valuation_api\mcp_servers -Recurse -Include "__pycache__" -Directory | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Push-Location valuation_api

$envVars = "GOOGLE_CLOUD_PROJECT=$PROJECT,VALUATION_API_KEY=$ApiKey"

$deployArgs = @(
    "run", "deploy", $SERVICE,
    "--source", ".",
    "--region", $REGION,
    "--project", $PROJECT,
    "--service-account", $SA_EMAIL,
    "--allow-unauthenticated",
    "--set-env-vars", $envVars,
    "--memory", "512Mi",
    "--cpu", "1",
    "--min-instances", "0",
    "--max-instances", "5",
    "--timeout", "60",
    "--port", "8080"
)

try {
    & gcloud @deployArgs
    $deployExit = $LASTEXITCODE
} finally {
    Pop-Location
    if (Test-Path valuation_api\mcp_servers) { Remove-Item -Recurse -Force valuation_api\mcp_servers }
}

if ($deployExit -ne 0) {
    Write-Host "Deploy failed" -ForegroundColor Red
    exit 1
}

Write-Host ""
$url = & gcloud run services describe $SERVICE --region $REGION --project $PROJECT --format "value(status.url)"
Write-Host "Service URL: $url" -ForegroundColor Green
Write-Host ""
Write-Host "For Decomind (Azure) config:" -ForegroundColor Yellow
Write-Host "  VALUATION_API_URL = $url"
Write-Host "  VALUATION_API_KEY = $ApiKey"
