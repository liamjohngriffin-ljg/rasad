# Rasad: local run on Windows. Needs Python 3.11+ only (the front end is pre-built in backend\static).
#   cd $HOME\Downloads\rasad
#   Set-ExecutionPolicy -Scope Process Bypass -Force; .\run-windows.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\backend
$py = $null
foreach ($cand in @(@("py","-3"), @("python"), @("python3"))) {
  try {
    $v = & $cand[0] @($cand[1..($cand.Length-1)] | Where-Object { $_ }) --version 2>&1
    if ($LASTEXITCODE -eq 0 -and "$v" -match "Python 3\.(1[1-9]|[2-9][0-9])") { $py = $cand; break }
  } catch {}
}
if (-not $py) {
  Write-Host "Python 3.11 or newer was not found. Install it, then close and reopen PowerShell and run this again." -ForegroundColor Yellow
  Write-Host "  Option A: double-click python-manager-26.4.msix in Downloads, click Install, then run:  py install default"
  Write-Host "  Option B: https://www.python.org/downloads/  (tick 'Add python.exe to PATH')"
  exit 1
}
$exe = $py[0]; $args0 = @($py[1..($py.Length-1)] | Where-Object { $_ })
Write-Host "== Using $exe $args0 ($(& $exe @args0 --version))" -ForegroundColor Cyan
Write-Host "== Installing Python packages (first run takes a minute)" -ForegroundColor Cyan
& $exe @args0 -m pip install --quiet --disable-pip-version-check -e ".[dev]"
if (-not (Test-Path "rasad.db")) {
  Write-Host "== Seeding demo data" -ForegroundColor Cyan
  & $exe @args0 -m rasad.seed.load 2026-10-18
}
$env:RASAD_STATIC_DIR = (Resolve-Path ".\static").Path
$env:RASAD_DATA_DIR = (Resolve-Path ".").Path + "\data"
New-Item -ItemType Directory -Force -Path $env:RASAD_DATA_DIR | Out-Null
foreach ($lic in @("$PSScriptRoot\licence.json", "$PSScriptRoot\..\licence.json")) {
  if ((Test-Path $lic) -and -not (Test-Path "$env:RASAD_DATA_DIR\licence.json")) { Copy-Item $lic "$env:RASAD_DATA_DIR\licence.json"; Write-Host "== Licence installed from $lic" -ForegroundColor Cyan }
}
if (-not (Test-Path "data\.backfilled")) {
  Write-Host "== First run: fetching live data (PortWatch, UKMTO, JMIC, UK sanctions, QNA); needs internet, takes a few minutes" -ForegroundColor Cyan
  & $exe @args0 -m rasad.pipelines.run backfill
  New-Item -ItemType File -Force -Path "data\.backfilled" | Out-Null
}
if (-not $env:RASAD_ADMIN_PASSWORD) { $env:RASAD_ADMIN_PASSWORD = "change-me-on-first-login" }
Write-Host "== Starting Rasad on http://localhost:8000 (sign in as admin / $env:RASAD_ADMIN_PASSWORD; close this window to stop)" -ForegroundColor Cyan
Start-Job -ScriptBlock { Start-Sleep -Seconds 4; Start-Process "http://localhost:8000" } | Out-Null
# the scheduler polls the feeds every few hours and commits the day's forecasts at 06:00 while this window is open
$env:RASAD_POLL_INTERVAL_HOURS = "4"
Start-Job -ArgumentList $exe, $args0, (Get-Location).Path, $env:RASAD_DATA_DIR -ScriptBlock {
  param($exe, $a, $dir, $data)
  Set-Location $dir; $env:RASAD_DATA_DIR = $data; $env:RASAD_MODEL_PROVIDER = "rules"; $env:RASAD_POLL_INTERVAL_HOURS = "4"
  & $exe @a -m rasad.pipelines.scheduler
} | Out-Null
& $exe @args0 -m uvicorn rasad.api.app:app --port 8000
