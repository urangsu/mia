# NAVER PC source and report cards

## Metal-first horizontal cards (2026-10-30)

- HTML order: metals, FX, four rates, market indicators, combined equities/capitalization.
- First available Ni, Co, lithium carbonate and Mn appear before extra quotes and Payables. No observations are merged or replaced.
- Computer Use synthetic preview: horizontal range 806px, keyboard scrollLeft 258px; no document overflow.
- Stored synthetic history: selection opens one history beneath the carousel, with two valid observations, no document overflow.
- Regression suite: 465 tests pass. This is not company Windows/ECM or subscribed-session acceptance.

Observed with Computer Use in the in-app browser, without login:

- Company AA- 3-year: stock.naver.com/marketindex/domesticInterest/KFIA103009/price
- Korean 3-year: stock.naver.com/marketindex/bond/KR3YT=RR/price
- US and Korean government bond lists; domestic interest and FX navigation.

The first DOM snapshot contained placeholder zeroes/empty tables. Loaded daily
tables contained explicit full dates and closes. Both real minimal DOM samples
parsed 20 rows with no parser warning. Real source prices/DOM stay outside Git.
No login, private API, cookie transfer or port/profile change was performed.
DOM Inspector archive was not installed/executed in this browser; Computer Use's
read-only rendered-DOM access supplied equivalent inspection, not extension E2E.

Added source-bound routes for KR3Y and KR_CORP_AA_3Y, percent-unit guards and
government/corporate provenance separation. Today rows remain excluded. These
extra instruments do not turn the existing required-eight source contract into
an equality failure. Source holidays remain explicitly calendar-unverified.

HTML presentation: one stock/cap table with rank, linked name, market cap, price,
absolute change and one-decimal percentage. Joins require code and date; an undated
capture may use the latest observed close strictly before its capture day, with
snapshot/close distinction in the caption. No matching close yields —, not zero.
Original snapshot tables are retained in collapsed audit output.

Metal/FX/market grids use bordered responsive cards, numeric emphasis, local system
type, inline units, and restrained red/blue changes. Yield cards keep 3-decimal
levels and 1-decimal bp changes. Historical metal expansion remains available.
No source styling, logos or fonts are copied. Light default and top dark switch
are retained. Synthetic preview verified no horizontal overflow and closed audit.

Verification: full suite 462 tests (macOS/Qt offscreen); synthetic browser preview
and real public DOM parsing are separate evidence. Company Windows Selenium
collection/SQLite/report/ECM end-to-end acceptance is not claimed. KOSPI flows,
DXY, API summary and PPTX card-layout parity remain outside this completed slice.
GitHub/source-bundle publication is not implied by this working-tree report.
