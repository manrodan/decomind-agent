# Despliega los 4 MCP servers a Cloud Run.
#
# Pre-requisitos:
#   - gcloud auth login
#   - gcloud config set project decomind-agent-challenge
#   - Cloud Run, Cloud Build, Artifact Registry APIs habilitadas
#
# Uso:
#   .\scripts\deploy_mcps.ps1
#
# La primera vez tarda ~3-5 min por servicio. Re-deploys más rápidos por cache.

$ErrorActionPreference = "Stop"

$PROJECT  = "decomind-agent-challenge"
$REGION   = "europe-west1"
$SA_NAME  = "decomind-agent-dev"
$SA_EMAIL = "$SA_NAME@$PROJECT.iam.gserviceaccount.com"

$services = @(
    @{ name = "mcp-geocoding";        module = "geocoding" }
    @{ name = "mcp-market-research";  module = "market_research" }
    @{ name = "mcp-renovation";       module = "renovation" }
    @{ name = "mcp-dossier-pdf";      module = "dossier_pdf" }
    @{ name = "mcp-catastro";         module = "catastro" }
    @{ name = "mcp-notariado";        module = "notariado" }
)

foreach ($svc in $services) {
    $name   = $svc.name
    $module = $svc.module
    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Cyan
    Write-Host "  Deploying $name (MCP_SERVICE=$module)"                  -ForegroundColor Cyan
    Write-Host "========================================================" -ForegroundColor Cyan
    Write-Host ""

    $envVars = "MCP_TRANSPORT=http,MCP_SERVICE=$module,GOOGLE_CLOUD_PROJECT=$PROJECT"

    # PDF MCP necesita bucket de outputs
    if ($module -eq "dossier_pdf") {
        $envVars += ",DOSSIER_BUCKET=decomind-agent-dossiers"
    }

    $args = @(
        "run", "deploy", $name,
        "--source", ".",
        "--region", $REGION,
        "--project", $PROJECT,
        "--service-account", $SA_EMAIL,
        "--no-allow-unauthenticated",
        "--set-env-vars", $envVars,
        "--memory", "512Mi",
        "--cpu", "1",
        "--min-instances", "0",
        "--max-instances", "3",
        "--timeout", "60",
        "--port", "8080"
    )

    & gcloud @args

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Deploy de $name fallo - abortando" -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  Todos los servicios desplegados"                         -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green
Write-Host ""
Write-Host "URLs de los servicios:" -ForegroundColor Yellow

foreach ($svc in $services) {
    $url = & gcloud run services describe $svc.name `
        --region $REGION `
        --project $PROJECT `
        --format "value(status.url)"
    Write-Host ("  {0,-22} {1}" -f $svc.name, $url)
}
