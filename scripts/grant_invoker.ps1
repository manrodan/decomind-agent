# Concede roles/run.invoker en cada MCP Cloud Run service.
#
# Por defecto concede a info@decomind.es. Cambia $MEMBER si invocas desde otro
# usuario o desde un service account.
#
# Uso:
#   .\scripts\grant_invoker.ps1
#   .\scripts\grant_invoker.ps1 -Member "serviceAccount:my-sa@my-project.iam.gserviceaccount.com"

param(
    [string]$Member = "user:info@decomind.es"
)

$ErrorActionPreference = "Stop"

$PROJECT = "decomind-agent-challenge"
$REGION  = "europe-west1"

$services = @(
    "mcp-geocoding",
    "mcp-market-research",
    "mcp-renovation",
    "mcp-dossier-pdf"
)

Write-Host "Granting roles/run.invoker on 4 services to $Member" -ForegroundColor Cyan

foreach ($svc in $services) {
    Write-Host "  $svc ..." -NoNewline
    $args = @(
        "run", "services", "add-iam-policy-binding", $svc,
        "--region", $REGION,
        "--project", $PROJECT,
        "--member", $Member,
        "--role", "roles/run.invoker",
        "--quiet"
    )
    & gcloud @args | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host " FAILED" -ForegroundColor Red
        exit 1
    }
    Write-Host " OK" -ForegroundColor Green
}

Write-Host "`nDone." -ForegroundColor Green
