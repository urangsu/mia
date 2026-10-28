# Metal history and SMM implementation plan

> Inline execution: user approved the single metal table, expandable history,
> source link inside expansion, and nickel equivalent = sulphate /0.2232.

**Goal:** One metal report table with usable stored-history charts and a real
public SMM collection path for three explicitly identified instruments.

**Architecture:** Keep immutable ReportContext and all existing source roles.
SMM gets a separate public DOM parser/storage table and independently cancellable
pipeline stage. Raw and derived prices have distinct identities. HTML histories
reuse validated dashboard series; no private API, login bypass or fake backfill.

**Tech Stack:** Python/SQLite/Selenium/Jinja, inline SVG and browser-native JS.

## Approved spec and limits

Single metal table includes real per-row dates (mixed dates cannot share a false
as-of date). Click names to open a chart and dated numeric history immediately
below the row. Gaps remain gaps. One observation is a point, not an invented line.
Source links move inside the expansion. HTML stays self-contained and themed.

SMM public homepage DOM verified with Computer Use on2026-10-28. Exact codes:
SMM-Li-LC-001, SMM-NI-NC-001, SMM-CO-CM-001. Public table has USD/tonne average,
change and source date. Product historical pages require login: no attempt to
extract locked data. Each daily run accumulates only the observed public quote.
Tax basis is unspecified by this homepage, not inferred. Nickel equivalent is
explicitly derived at user-supplied22.32%, unitUSD/t Ni; it is not a nickel spot quote.

## Tasks

- [ ] Tests: unified metal cardinality, correct dates, chart identity/gaps,
  historyless rows and safe serialized payload. Run failures before implementation.
- [ ] report_presentation.py: replace date-grouped metal tables with one table;
  add history payload from dashboard_data(context), match exact code/unit/mode.
- [ ] report_template.html: accessible row toggle, bounded SVG chart, hover/focus
  value readout and date range controls. Raw provenance remains bottom closed.
- [ ] smm_public.py + test_smm_public.py: parse only exact homepage table rows,
  validate date/unit/product href; quarantine conflicts; preserve revision history.
  Formula test: Decimal('2232')/Decimal('.2232') == Decimal('10000').
- [ ] smm_reporting.py + integration tests: same read-transaction snapshot,
  separate raw/derived series, daily/monthly metal accumulation and report context.
- [ ] pipeline_v37.py/app_settings.py/desktop_ui.py/CLI: explicit SMM switch,
  independent stage, no background use when absent/disabled, owned tab cleanup.
- [ ] Actual public DOM replay through parser/storage/report; keep real price DOM
  outside Git and synthetic source fixtures in tests. Browser test clickable history.
- [ ] Full regression, source-only bundle/restore verification. Company Windows
  acceptance remains separate; no unrequested remote push/merge.
