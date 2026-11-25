# Runs Falcon Eye's security checks on Windows. Run from the project folder:
#   .\scripts\security_scan.ps1
# Needs: the Python virtual environment active, Docker running with the app up
# (docker compose up -d), and Node installed. Reports go to the reports\ folder.
$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Force reports | Out-Null

Write-Host "`n[1/5] Installing scanners..." -ForegroundColor Cyan
python -m pip install -q -r requirements-security.txt

Write-Host "`n[2/5] Bandit (Python code scan)..." -ForegroundColor Cyan
python -m bandit -r . -x ./tests,./frontend,./legacy_backup,./.venv,./venv -ll -f txt -o reports\bandit.txt
Get-Content reports\bandit.txt | Select-String -Pattern "Issue:|Total issues|Severity: " | Select-Object -First 30

Write-Host "`n[3/5] pip-audit (Python dependencies)..." -ForegroundColor Cyan
python -m pip_audit -r requirements.txt 2>&1 | ForEach-Object { "$_" } | Tee-Object reports\pip-audit.txt

Write-Host "`n[4/5] npm audit (frontend dependencies)..." -ForegroundColor Cyan
Push-Location frontend
npm audit --omit=dev 2>&1 | Tee-Object ..\reports\npm-audit.txt
Pop-Location

Write-Host "`n[5/5] OWASP ZAP baseline scan of http://localhost:8080 ..." -ForegroundColor Cyan
Write-Host "(This only scans your own local copy. Never scan sites you do not own.)"
docker run --rm -v "${PWD}\reports:/zap/wrk:rw" -v "${PWD}\.zap:/zap/rules:ro" -t zaproxy/zap-stable `
  zap-baseline.py -t http://host.docker.internal:8080 -c /zap/rules/rules.tsv -r zap-report.html -J zap-report.json -I

Write-Host "`nDone. Open reports\zap-report.html in your browser. Paste the WARN-NEW / FAIL-NEW lines here for help." -ForegroundColor Green
