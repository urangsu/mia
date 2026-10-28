# Single metal table, SMM and existing ECM matrix

Implemented: one main metal table with actual dates, click-to-expand stored history
in HTML and desktop, inline units, preserved light/dark controls and collapsed audit.
History gaps are not forward-filled; a single observation renders as a point.

SMM collection uses the public metal.com homepage, exact known instrument links
and explicit dates/units. It does not access login-only histories. Three raw series
are stored independently; nickel equivalent divides sulphate by the user-specified
0.2232. It is not labelled a native nickel spot quote. VAT is not inferred.
Public-source availability and permitted reuse remain subject to the publisher.

Live evidence on 2026-10-28: Computer Use read the public homepage's three rows;
minimal real DOM was replayed through parser, temporary SQLite and HTML rendering.
Three raw plus one derived series appeared. Real prices, DB and DOM remain outside
Git. Synthetic HTML browser checks covered toggle, month filter, gaps and keyboard
readout. This is not a company Chrome/Selenium/ECM end-to-end run.

The photo matrix path uses headers 1/3, optional subtype row2, and ABC dates from
row5. TODAY row4, existing formulas, unspecified VAT-excluded columns, and all
unrelated sheets/data are preserved. XLSM uses the already-open Excel instance,
Save (not SaveAs), format/VBA-presence checks, target identity and approval fingerprint.
See ECM_PHOTO_MATRIX_KO.md for company acceptance steps.

Regression command (Qt offscreen on this Mac):

    QT_QPA_PLATFORM=offscreen python -m unittest discover -q

No claim is made that offline/mocked tests prove company SSO, secure Excel write
or ECM check-in. Browser ports 9222/9337 and their profiles were not used.
