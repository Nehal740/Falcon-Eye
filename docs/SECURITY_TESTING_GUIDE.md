# Security testing guide

## 1. Automated regression tests (safe, offline)

```powershell
python -m pytest tests/test_security_owasp.py -v     # OWASP tests only
python -m pytest                                      # everything
```

## 2. Full scan on Windows (one command)

Start the app first (`docker compose up -d`, wait 30 seconds), activate the virtual
environment, then run each command **on its own line**:

```powershell
.\scripts\security_scan.ps1
```

If PowerShell blocks scripts: `Set-ExecutionPolicy -Scope Process Bypass`.
It runs Bandit (code), pip-audit (Python packages), npm audit (frontend packages) and
OWASP ZAP baseline (running site). Reports are saved in `reports\` (git-ignored).
Open `reports\zap-report.html` in a browser.

ZAP alone:

```powershell
docker run --rm -t zaproxy/zap-stable zap-baseline.py -t http://host.docker.internal:8080
```

## 3. Reading results

- ZAP `FAIL-NEW` = fix it. `WARN-NEW` = read it; many are informational for a single-page app.
- To ignore a finding on purpose, add its rule id to `.zap/rules.tsv` with a written reason.
- The baseline scan is **passive**: it does not attack. Never scan systems you do not own.

## 4. In GitHub

`.github/workflows/security.yml` runs the tests, Bandit, pip-audit, npm audit and a ZAP scan
on every push and every Monday. Reports are attached to the run.

## 5. What these checks cannot prove

They find known patterns and known vulnerable packages. They do not replace a manual
penetration test or a code review by a person.
