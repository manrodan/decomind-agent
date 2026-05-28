# Despliega el frontend Web UI a Cloud Run.
#
# Modelo: el frontend ejecuta el agente ADK DIRECTAMENTE (sin pasar por Agent
# Engine), y los toolsets HTTP llaman a los 4 MCP Cloud Run usando la identidad
# de la SA decomind-agent-dev (vía metadata server).
#
# Pre-deploy: copia agent/ y mcp_servers/ dentro de frontend/ para que estén en
# el build context. Limpia tras el deploy (los originales del repo no cambian).

$ErrorActionPreference = "Stop"

$PROJECT  = "decomind-agent-challenge"
$REGION   = "europe-west1"
$SA_NAME  = "decomind-agent-dev"
$SA_EMAIL = "$SA_NAME@$PROJECT.iam.gserviceaccount.com"
$SERVICE  = "decomind-agent-ui"

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Deploying $SERVICE (direct-ADK mode)"                    -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

# Pre-copia: agent/ y mcp_servers/ al frontend/ (build context).
# Si existen ya, los borramos primero (rebuild limpio).
if (Test-Path frontend\agent) { Remove-Item -Recurse -Force frontend\agent }
if (Test-Path frontend\mcp_servers) { Remove-Item -Recurse -Force frontend\mcp_servers }

Write-Host "Copying agent/ and mcp_servers/ into frontend/ build context..." -ForegroundColor Yellow
Copy-Item -Recurse -Force agent frontend\agent
Copy-Item -Recurse -Force mcp_servers frontend\mcp_servers

# Borra cachés Python para no inflar la imagen
Get-ChildItem -Path frontend\agent, frontend\mcp_servers -Recurse -Include "__pycache__" -Directory `
    | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# MCP URLs — leemos del .env.cloud si existe, si no de las variables de entorno
$mcpVars = @{}
if (Test-Path .env.cloud) {
    Get-Content .env.cloud | ForEach-Object {
        if ($_ -match '^(MCP_\w+)=(.+)$') {
            $mcpVars[$matches[1]] = $matches[2].Trim()
        }
    }
}
if ($mcpVars.Count -lt 4) {
    Write-Host "WARN: missing MCP URLs in .env.cloud — fetching from Cloud Run" -ForegroundColor Yellow
    $services = @(
        @{ env = "MCP_GEOCODING_URL";       name = "mcp-geocoding" }
        @{ env = "MCP_MARKET_RESEARCH_URL"; name = "mcp-market-research" }
        @{ env = "MCP_RENOVATION_URL";      name = "mcp-renovation" }
        @{ env = "MCP_DOSSIER_PDF_URL";     name = "mcp-dossier-pdf" }
    )
    foreach ($svc in $services) {
        $url = & gcloud run services describe $svc.name --region $REGION --project $PROJECT --format "value(status.url)"
        $mcpVars[$svc.env] = $url
    }
}

$envVars = "GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=$REGION,AGENT_MODEL=gemini-2.5-flash"
foreach ($k in $mcpVars.Keys) {
    $envVars += ",$k=$($mcpVars[$k])"
}

Push-Location frontend

$args = @(
    "run", "deploy", $SERVICE,
    "--source", ".",
    "--region", $REGION,
    "--project", $PROJECT,
    "--service-account", $SA_EMAIL,
    "--allow-unauthenticated",
    "--set-env-vars", $envVars,
    "--memory", "1Gi",
    "--cpu", "1",
    "--min-instances", "0",
    "--max-instances", "5",
    "--timeout", "600",
    "--port", "8080"
)

try {
    & gcloud @args
    $deployExit = $LASTEXITCODE
} finally {
    Pop-Location
    # Clean up copia para no contaminar el repo
    if (Test-Path frontend\agent) { Remove-Item -Recurse -Force frontend\agent }
    if (Test-Path frontend\mcp_servers) { Remove-Item -Recurse -Force frontend\mcp_servers }
}

if ($deployExit -ne 0) {
    Write-Host "Deploy fallo" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "URL del servicio:" -ForegroundColor Yellow
$url = & gcloud run services describe $SERVICE --region $REGION --project $PROJECT --format "value(status.url)"
Write-Host "  $url" -ForegroundColor Green
Write-Host ""
Write-Host "Abre en navegador:" -ForegroundColor Yellow
Write-Host "  $url"
