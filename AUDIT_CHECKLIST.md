# Project audit checklist

## Files and data

- [x] Inspected source tree and compared the existing ZIP manifest with the project contents.
- [x] Read the complete three-page assignment PDF and checked its required incident scenarios and report date.
- [x] Confirmed all four source CSVs are included; sales cover 7 Sep-15 Nov 2026 and POs end 9 Nov 2026.
- [x] Counted 765 exact duplicate sales rows; removed and logged them.
- [x] Normalized 64 dark-store city labels with case/spelling variants; logged the decision.
- [x] Verified no source missing cells, invalid dates, duplicate PO IDs, unmapped sales stores, unmapped platform product IDs, or sales/store platform mismatches.
- [x] Checked row quantity validity, `sales_inr` versus units times price, duplicate dimension mappings, and PO weekly combination coverage.
- [x] Preserved missing PO weeks as absent records; coverage ranges from 99.26% to 100% of expected warehouse-SKU combinations.

## Analytical formulas and business incidents

- [x] Weighted fill rate uses sum(delivered) / sum(ordered); shortfall is max(ordered - delivered, 0).
- [x] Revenue change guards division by zero and keeps missing baselines unknown.
- [x] Revenue gap uses a fixed pre-incident baseline and actual `sales_inr`; assumptions are in evidence and PDF.
- [x] Validated six Blinkit Bengaluru SKUs, six low-fill weeks from 21 Sep through 26 Oct, cumulative units and two-week recovery.
- [x] Validated Zepto Bengaluru Neem Face Wash 100ml rank baseline 2.97, decline beginning 12 Oct, rank 13.25 by 9 Nov, sales and availability context.
- [x] Validated two Instamart Hyderabad sunscreen SKU PO gaps on 14 and 21 Sep, subsequent PO resumption, availability and sales deterioration.
- [x] Did not present the separate Zepto Mumbai end-of-export missing-row pattern as a confirmed interruption because sales did not deteriorate and no resumption is observed.
- [x] Added unique alert IDs, severity, evidence, affected period, status, team, recommendation and explainable score; symptoms within incident windows are suppressed from separate sales alerts.

## Application, report and submission

- [x] Kept the six existing Streamlit workspaces and added full-alert filtering/evidence alongside the top-15 overview.
- [x] Generated a three-page PDF with compact supply, ranking, ordering-gap and methodology sections; rendered all pages to PNG and visually inspected them.
- [x] Added 14 automated tests, including actual-data regression tests for all three incidents.
- [x] Added data quality, audit trail, PO weekly coverage, full alert, top alert, supply incident, ranking incident, weekly KPI and ordering gap exports.
- [x] Regenerated final outputs after the final alert logic; 14 automated tests pass, Python files compile, and the live Streamlit Executive Overview loads actual KPIs.
- [x] Rendered and visually inspected all three final PDF pages; report shows 16 November 2026 and coverage through 15 November 2026.
- [ ] Save actual screenshots for all six dashboard pages. Browser automation saving is blocked in this environment; manual instructions are in `screenshots/README.md`.
- [x] Built and checked `JOY_QUICK_COMMERCE_SUBMISSION_FINAL.zip`; it contains the runnable project, supplied data, tests, outputs and documentation while excluding caches and temporary rendered pages.
