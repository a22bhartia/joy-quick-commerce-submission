# Joy Quick Commerce Intelligence

An explainable Streamlit decision-support dashboard and automated Monday report for Joy's supplied quick-commerce exports. The report date is 16 November 2026; sales data ends Sunday, 15 November, and purchase orders end 9 November.

## Features

- Six dashboard workspaces: Executive Overview, Supply Chain Intelligence, Sales & Availability, Search & Discoverability, Platform Ordering Gaps, and Action Centre.
- Weekly PO fill rate, shortfalls, sustained supply episodes, platform ordering gaps, historical search-rank deterioration, sales changes and availability signals.
- Incident-level alert IDs, priority, category, location, SKU, dates, affected-week duration, evidence, estimated exposure, team, action and status.
- The executive view presents the top 15 alerts. The Action Centre filters all findings and supports CSV download.
- PDF report, full alert export, executive shortlist, weekly KPI and PO exports, data quality audit and tests.

## Technology and folder layout

Python, Pandas, NumPy, Streamlit, Plotly and ReportLab.

```text
app.py                          Streamlit application
analytics.py                    Weekly sales, PO, rank and availability analysis
data_cleaning.py                Normalization, joins, validation and audit trail
alerts.py                       Incident detection, evidence, scoring and ranking
report_generator.py             Paginated Monday PDF generation
generate_outputs.py             Rebuild CSV outputs and PDF
config.py                       Reporting dates and score thresholds
data/                           Four supplied source CSVs
outputs/                        Alerts, incidents, KPI, coverage and data quality CSVs
screenshots/                    Screenshot instructions/status
tests/                          Synthetic unit fixtures and actual-data regression checks
Monday_16_November_2026_Report.pdf
```

## Install and run

From this directory:

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

Rebuild the outputs and PDF:

```bash
python generate_outputs.py
```

Run all automated checks:

```bash
python -m unittest discover -s tests -v
```

## Input data and cleaning

Place `daily_sales.csv`, `dark_stores.csv`, `products.csv`, and `purchase_orders.csv` in `data/`. Sales map using `(platform, platform_product_id)` to the internal SKU. Stores map through `dark_store_id` to platform warehouse and city. Platform aliases, identifier whitespace, city case variants and common city spellings are normalized before joins. Exact duplicate rows are counted and removed. Invalid critical numeric rows are counted in `outputs/invalid_values.csv` and excluded from calculations; invalid availability, rank or price values remain missing signals rather than being filled with zero. `outputs/audit_trail.csv`, `data_quality.csv`, and `mapping_quality.csv` show the cleaning and join results.

Current source profile: `daily_sales.csv` has 186,285 rows including 765 exact duplicate rows; 185,520 are retained. `dark_stores.csv` has 202 rows, `products.csv` has 45 platform-product mappings, and `purchase_orders.csv` has 2,694 rows. No source missing cells or invalid dates were found. All sales store and product joins succeeded; no duplicate PO IDs were found. Weekly PO combination coverage is reported separately because missing PO rows are part of the incident analysis.

## Analytical rules

- Weeks run Monday through Sunday. Fill rate is delivered units divided by ordered units; shortfall is ordered less delivered units, floored at zero. Fill rate is quantity-weighted, not an average of percentages.
- Sustained supply incidents require at least three consecutive observed weekly PO fill rates below 90%. Each issue includes affected period, cumulative ordered/delivered/short units, status, store availability and city-SKU sales context. Current, recently resolved and historical episodes remain visible.
- Search rank uses lower-is-better semantics. The historical baseline is the mean rank in the first four observed weeks for that platform-city-SKU. A deterioration of five or more positions is tracked across weeks; a large sudden shift is not discarded simply because subsequent weeks remain poor.
- A PO gap requires prior ordering, at least two consecutive absent rows, at least 95% expected warehouse-SKU combination coverage in each missing week, and either a later resumed order or corroborating severe stock/sales deterioration. Missing rows remain absent, never treated as observed zero quantity. A product with no prior order history is not flagged.
- Availability is a supplied stock-out signal, not inventory on hand. Availability below 50% is a review threshold.
- Revenue estimates hold a pre-incident weekly sales baseline fixed across the event, compare with actual `sales_inr` during affected weeks and sum positive weekly gaps. At least two pre-event weeks are required except the September Instamart scenario, which only has one and is explicitly less certain. Estimates are not causal claims or confirmed lost revenue. The Executive KPI `latest-week revenue gap` uses the preceding four observed weekly means for the latest sales week; it is not a confirmed current run rate.
- Alert score is 30% severity, 25% revenue-impact percentile, 20% duration (capped at six weeks), 15% affected-store footprint and 10% product-importance percentile. Priority is Critical at 75+, High at 50+, otherwise Medium. The components and cutoffs are in `config.py`.

## Findings validated against the supplied exports

- Blinkit Bengaluru: six SKUs had fill rates below 90% in six consecutive PO weeks from 21 September through 26 October. Together they had 5,820 units ordered, 3,042 delivered, 2,778 short and 52.3% weighted fill. Latest two PO weeks recovered above 90%, so the incident is marked recently resolved. City availability across the event averaged about 35-53% for those SKUs compared with about 89-92% before it.
- Zepto Bengaluru: Neem Face Wash 100ml moved from a first-four-week rank baseline of 2.97 to 10 on 12 October and 13.25 on 9 November. It stayed at rank 10+ for five weeks. Affected-week sales totalled INR 42,302 versus a fixed pre-event baseline of INR 16,380 per week; availability averaged 90.4% versus 91.8% before the decline.
- Instamart Hyderabad: both sunscreen SKUs have no PO rows on 14 and 21 September, with orders resuming on 28 September. Weekly order-combination coverage was 99.3% across the gap. Availability fell from 92-95% to 36-41%. Only one prior weekly PO is available before the gap, so interruption and revenue exposure remain inferred and require KAM confirmation.

## Limitations and screenshot capture

PO data ends 9 November, so ordering after that date cannot be checked. No discontinuation status or exact store inventory is supplied. Incomplete/missing PO records cannot be proven as zero orders; the alert evidence exposes coverage and labels inferences. The `screenshots/README.md` contains manual capture steps. Automated screenshot saving was blocked by the browser-control policy in this environment; no placeholder images are included.
