"""Regenerate CSV outputs and the Monday report from current input files."""
import json
from config import OUTPUT_DIR, ROOT
from data_cleaning import load_data
from analytics import analyze, kpis
from alerts import build_alerts, ordering_gaps, po_weekly_coverage
from report_generator import generate_report

def main():
    data,quality=load_data(); analysis=analyze(data); alerts=build_alerts(analysis); gaps=ordering_gaps(data); summary=kpis(analysis)
    alerts.to_csv(OUTPUT_DIR/'alerts.csv',index=False)
    alerts.head(15).to_csv(OUTPUT_DIR/'top_alerts.csv',index=False)
    analysis['weekly_sales'].to_csv(OUTPUT_DIR/'weekly_kpis.csv',index=False)
    analysis['po_weekly'].to_csv(OUTPUT_DIR/'purchase_order_analysis.csv',index=False)
    gaps.to_csv(OUTPUT_DIR/'ordering_gaps.csv',index=False)
    po_weekly_coverage(data).to_csv(OUTPUT_DIR/'po_weekly_coverage.csv',index=False)
    analysis['commercial_weekly'].to_csv(OUTPUT_DIR/'product_city_weekly.csv',index=False)
    alerts[alerts.category.eq('Sustained supply under-delivery')].to_csv(OUTPUT_DIR/'supply_incidents.csv',index=False)
    alerts[alerts.category.eq('Search visibility deterioration')].to_csv(OUTPUT_DIR/'ranking_incidents.csv',index=False)
    (OUTPUT_DIR/'kpis.json').write_text(json.dumps(summary,indent=2))
    generate_report(analysis,alerts,summary,ROOT/'Monday_16_November_2026_Report.pdf',quality=quality,data=data)
    print(f"Generated {len(alerts)} prioritized alerts; revenue INR {summary['revenue_inr']:,}; units {summary['units_sold']:,}")
if __name__=='__main__': main()
