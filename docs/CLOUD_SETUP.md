# Codex cloud setup

Repository: `urangsu/mia`, branch `main`. Source is at the repository root.

## Environment fields

Install script:

```bash
cd /workspace/mia
bash scripts/codex_setup.sh
```

Start skill:

```text
Read /workspace/mia/AGENTS.md and docs/CODEX_WORK_ORDER.md.
Use /workspace/mia/.venv/bin/python for project commands.
Run bash /workspace/mia/scripts/codex_check.sh to verify readiness.
This is a Windows desktop collector, not a web service. Do not launch the GUI,
Chrome, Excel, a Windows scheduled task, or ECM in the headless cloud setup.
Continue P0 investigation and offline regression; keep live Windows acceptance separate.
```

No application secrets are needed for setup. Keep environment sharing private and preserve existing network restrictions. Package-manager access is enough for dependency installation. Public NAVER inspection may require separately authorized source-domain access; do not broadly enable arbitrary networking or upload company data.

Save the draft, run/verify installation on the refreshed repository and publish only after it succeeds. A saved configuration and a published prepared environment are not the same state. If the existing setup still sees an empty repository, refresh the repository through the environment's supported flow before installation; do not reset or overwrite uncommitted work.

Official reference: https://learn.chatgpt.com/docs/environments/cloud-environments

## First development task

```text
Read AGENTS.md and docs/CODEX_WORK_ORDER.md and continue Fastmarkets v3.7.
Establish the fresh offline baseline first, then investigate P0 gaps. NAVER must
compare confirmed previous/preceding trading-day closes; target Windows 08:30 KST.
Keep Chrome 9222 and admin Edge 9337 isolated. Report live Windows/SSO/ECM checks
as unverified when unavailable. Provide source, tests and evidence, not just a plan.
```
