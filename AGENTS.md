# Project instructions

## Read before changing code

- Read README.md, README_V37.md, CHANGELOG_V37.md, VALIDATION_V37.md, HANDOFF_V37.md and docs/CODEX_WORK_ORDER.md.
- The repository is the extracted v3.7 baseline. Do not rebuild v3.2/v3.6 or assume the old recorded test count is a fresh result.
- Use Python 3.10+. Cloud development is headless; deployment is Windows with desktop Excel and company SSO. Never claim Windows/ECM acceptance from offline tests.

## Install and verify

```bash
bash scripts/codex_setup.sh
bash scripts/codex_check.sh
```

Both scripts use a repository-local `.venv`; no API keys or user profiles are needed. The check is offline and must not open browser sessions, register tasks or write ECM. A graphical smoke test is optional only when a display is available. For individual tests use `.venv/bin/python -m unittest discover -s . -p 'test_v37*.py' -v`.

## Safety and scope

- Never touch Chrome 9222, admin Edge 9337, pp.py/endp.py or unrelated browser sessions. Fastmarkets uses verified Chrome 9444 ownership/profile/CDP only.
- ECM uses the existing ordinary logged-in Edge through UI Automation. No debug Edge, profile/token/cookie copying, elevation or DRM/SSO bypass.
- No credentials, real DB/Excel, browser profiles or live logs in Git. Use synthetic fixtures and approved redacted samples.
- Preserve existing user workbook sheets/formulas/columns and company protection. Test actual writes only on authorized copies.
- NAVER compares two confirmed pre-capture market-day closes, not intraday quotes. Keep both dates/units/sources. Missing history stays missing; do not reverse-calculate old closes from quoted changes.
- The 08:30 Windows schedule requires a logged-in interactive user; cloud environment setup is not Windows scheduling.
- Do not add paid/private price APIs, news, AI commentary, mail delivery or unattended ECM approval.
- Approved public-close path: FinanceDataReader HTTP in an owned cancellable child, with exchange_calendars expected-session checks. This does not authorize private Fastmarkets APIs, KRX login bypass or browser/session changes. Preserve raw revisions/quarantine; never substitute older or adjusted closes for missing expected dates. See docs/FDR_CALENDARS_GUIDE.md.
- Read DESIGN_REFERENCE.md before UI/report changes. No proprietary brand assets/fonts.

## Working method

Reproduce each defect, add a failing test, make the smallest justified fix, rerun targeted and full regression. Keep original data and unrelated work intact. UI writes happen only on the main Tk thread; browser and COM shared resources must retain exclusive ownership. Do not remove verification to improve speed.

Parallel work, if explicitly used for this plan, must have separate file ownership and final integration review. Do not message other user-owned tasks or create unrelated tasks without user authorization.

## Completion

Separate static/mock/public-site/company-Windows/ECM-server evidence. Include exact commands, exit codes, measured performance and missing evidence. Report what is still unverified. Do not commit generated binaries or change repo visibility/network permissions. Source changes require reviewable commits; do not force-push or overwrite others' work.
