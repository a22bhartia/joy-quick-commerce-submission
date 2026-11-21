# Submission note - Joy Quick Commerce Intelligence

## What I chose to flag and why

The alert engine now keeps issue histories instead of only checking the latest PO week. It identified six Blinkit Bengaluru SKUs with six consecutive low-fill weeks (21 September-26 October): 5,820 units ordered, 3,042 delivered, 2,778 short, and a 52.3% weighted fill rate. The latest two PO weeks recovered above 90%, so these incidents are marked recently resolved. Zepto Bengaluru Neem Face Wash 100ml fell from a historical rank baseline of 2.97 to 10 on 12 October and 13.25 by 9 November, remaining poor for five weeks while average availability stayed near 90%. Instamart Hyderabad had two consecutive no-PO weeks for both sunscreen SKUs (14 and 21 September); orders resumed the week of 28 September, while availability and sales fell during the gap. This is an inferred pause supported by a near-complete export and store outcomes; the pre-gap PO history is only one week.

Priorities combine issue severity, revenue-impact percentile, duration, affected-store footprint and product importance. The executive shortlist is limited to 15, while the Action Centre retains all findings. Revenue exposure uses actual `sales_inr` against a fixed pre-incident weekly baseline: about INR 165,867 for the six Blinkit incidents, INR 39,598 for the Zepto rank deterioration, and INR 7,127 across the two Instamart gap windows. These are estimated sales gaps during flagged weeks, not confirmed lost revenue or an estimate of current run rate.

## Data quality and handling

The sales file had 765 exact duplicate rows out of 186,285. They were counted, removed, and written to the audit trail. Sixty-four dark-store city labels had case/spelling variants normalized. The other datasets had no exact duplicates; the files had no missing cells or invalid dates, and all sales store and platform-product mappings matched. PO exports have 99.3-100% expected warehouse-SKU combination coverage per week. The four absent Instamart sunscreen rows during the September gap were kept as absent records, not filled as zero quantities. Unknown signal values remain missing.

## AI use and checks

Codex was used for code generation, analysis, application development, debugging, tests and report generation. I manually checked the three incident histories against the source CSVs, the mappings, fill-rate and revenue-gap arithmetic, alert evidence, and rendered PDF pages. Fourteen automated tests cover formulas, missing values, mapping, alert uniqueness and the three actual-data regressions. The live Executive Overview was opened successfully and populated actual KPIs. The browser-control interface did not expose a supported way to save screenshots into the project; no screenshots are claimed. I did not claim manual visual verification of all six dashboard workspaces.
