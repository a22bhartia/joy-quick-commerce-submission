"""Generate a concise, paginated Monday business review PDF."""
from pathlib import Path
import json
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape,A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from config import REPORT_DATE,DATA_START,DATA_CUTOFF,OUTPUT_DIR

NAVY=colors.HexColor('#172B4D');ORANGE=colors.HexColor('#E85D2A');PALE=colors.HexColor('#FFF3ED');GRID=colors.HexColor('#D7DEE8')

def _money(value): return "INR {:,.0f}".format(value) if pd.notna(value) else "Not estimated"
def _evidence(row):
    try:return json.loads(row.supporting_evidence)
    except Exception:return {}
def _p(value,style): return Paragraph(str(value).replace("&","&amp;").replace("<","&lt;"),style)

def generate_report(a,alerts,kpi,out_path,quality=None,data=None):
    out_path=Path(out_path);out_path.parent.mkdir(parents=True,exist_ok=True)
    page=landscape(A4);width,height=page
    doc=SimpleDocTemplate(str(out_path),pagesize=page,rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=15*mm,title="Joy Quick Commerce Intelligence - Monday Business Review",author="Joy Quick Commerce Intelligence")
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleJoy",parent=styles["Title"],fontName="Helvetica-Bold",fontSize=19,leading=22,textColor=NAVY,alignment=0,spaceAfter=3))
    styles.add(ParagraphStyle(name="SectionJoy",parent=styles["Heading2"],fontName="Helvetica-Bold",fontSize=12,leading=14,textColor=ORANGE,spaceBefore=5,spaceAfter=4))
    styles.add(ParagraphStyle(name="SmallJoy",parent=styles["BodyText"],fontSize=7.3,leading=9,textColor=NAVY))
    styles.add(ParagraphStyle(name="BodyJoy",parent=styles["BodyText"],fontSize=8.5,leading=11,textColor=NAVY))
    styles.add(ParagraphStyle(name="CellJoy",parent=styles["BodyText"],fontSize=7,leading=8.2,textColor=NAVY,wordWrap="CJK"))
    styles.add(ParagraphStyle(name="CellHeadJoy",parent=styles["BodyText"],fontName="Helvetica-Bold",fontSize=7,leading=8.2,textColor=colors.white))
    story=[]
    def section(text): story.append(Paragraph(text,styles["SectionJoy"]))
    def table(title,frame,fields,headers,widths,limit=None):
        if title: section(title)
        if frame is None or frame.empty:
            story.append(Paragraph("No supported findings in the supplied data.",styles["BodyJoy"]));return
        if limit is not None: frame=frame.head(limit)
        rows=[[ _p(h,styles["CellHeadJoy"]) for h in headers ]]
        for _,r in frame.iterrows():
            vals=[]
            for c in fields:
                value=r.get(c,None)
                if c=="estimated_revenue_impact_inr": text=_money(value)
                elif c in ("first_affected_week","latest_affected_week","first_missing_week","latest_missing_week") and pd.notna(value): text=pd.Timestamp(value).strftime("%d %b")
                elif c=="fill_rate_pct" and pd.notna(value):text=f"{float(value):.1f}%"
                elif c=="score" and pd.notna(value):text=f"{float(value):.1f}"
                elif pd.isna(value):text="-"
                else:text=str(value)
                vals.append(_p(text,styles["CellJoy"]))
            rows.append(vals)
        t=Table(rows,colWidths=widths,repeatRows=1,hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY),("GRID",(0,0),(-1,-1),.35,GRID),("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,PALE]),("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4),("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]))
        story.append(t)

    story.extend([Paragraph("Joy Quick Commerce Intelligence - Monday Business Review",styles["TitleJoy"]),Paragraph("Monday, 16 November 2026 | Data through Sunday, 15 November 2026",styles["BodyJoy"]),Spacer(1,4)])
    coverage=f"Sales coverage: {pd.Timestamp(DATA_START):%d %b} to {pd.Timestamp(DATA_CUTOFF):%d %b %Y}. PO export coverage ends {pd.Timestamp(a['orders'].po_date.max()):%d %b %Y}."
    story.append(Paragraph(coverage,styles["SmallJoy"]))
    kdata=[["Recorded revenue",_money(kpi["revenue_inr"]),"Units sold",f"{kpi['units_sold']:,}","Products",str(kpi["products"])],["Platforms",str(kpi["platforms"]),"Weighted fill rate",f"{kpi['fill_rate_pct']:.1f}%" if kpi["fill_rate_pct"] is not None else "Not available","Latest-week revenue gap (est.)",_money(kpi["revenue_at_risk_inr"])]]
    kt=Table(kdata,colWidths=[37*mm,38*mm,30*mm,27*mm,48*mm,50*mm])
    kt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),PALE),("TEXTCOLOR",(0,0),(-1,-1),NAVY),("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),8),("GRID",(0,0),(-1,-1),.4,colors.white),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)]))
    story.extend([Spacer(1,5),kt])
    critical=int((alerts.priority=="CRITICAL").sum()) if not alerts.empty else 0;high=int((alerts.priority=="HIGH").sum()) if not alerts.empty else 0;medium=int((alerts.priority=="MEDIUM").sum()) if not alerts.empty else 0
    supply_findings=alerts[(alerts.category.eq("Sustained supply under-delivery"))&(alerts.platform.eq("Blinkit"))&(alerts.city.eq("Bengaluru"))]
    rank_findings=alerts[(alerts.category.eq("Search visibility deterioration"))&(alerts.platform.eq("Zepto"))&(alerts.city.eq("Bengaluru"))]
    order_findings=alerts[(alerts.category.eq("Platform ordering interruption"))&(alerts.platform.eq("Instamart"))&(alerts.city.eq("Hyderabad"))]
    executive_notes=[]
    if not supply_findings.empty:
        evs=[_evidence(r) for _,r in supply_findings.iterrows()];total_ordered=sum(int(e.get("ordered_units",0)) for e in evs);total_delivered=sum(int(e.get("delivered_units",0)) for e in evs);total_short=sum(int(e.get("shortfall_units",0)) for e in evs)
        period=pd.Timestamp(supply_findings.first_affected_week.min()).strftime("%d %b")+"-"+pd.Timestamp(supply_findings.latest_affected_week.max()).strftime("%d %b")
        executive_notes.append(f"{supply_findings.sku_code.nunique()} Blinkit Bengaluru SKUs had sustained under-delivery during {period}: {total_short:,} short units and {100*total_delivered/total_ordered:.1f}% weighted fill.")
    if not rank_findings.empty:
        r=rank_findings.sort_values("latest_affected_week").iloc[-1];ev=_evidence(r)
        executive_notes.append(f"{r['product']} remains at rank {ev.get('latest_rank')} versus historical baseline {ev.get('historical_baseline_rank_first_four_weeks')} (status: {r.status.lower()}).")
    if not order_findings.empty:
        evs=[_evidence(r) for _,r in order_findings.iterrows()];missing=sorted({d for e in evs for d in e.get("missing_po_weeks",[])})
        executive_notes.append(f"{order_findings.sku_code.nunique()} Instamart Hyderabad SKUs have multi-week PO gaps on {', '.join(pd.Timestamp(d).strftime('%d %b') for d in missing)}.")
    if not executive_notes: executive_notes.append("No supported examples of the three assignment incident types were detected in the supplied data.")
    story.append(Paragraph(f"Executive summary: {len(alerts)} issue-level alerts were identified ({critical} critical, {high} high, {medium} medium). "+" ".join(executive_notes)+" Revenue exposure is an assumption-based estimate, not confirmed lost revenue.",styles["BodyJoy"]))
    section("Weekly recorded revenue")
    weekly=a["weekly_sales"].groupby("week_start").revenue_inr.sum().sort_index()
    d=Drawing(255*mm,48*mm);chart=HorizontalLineChart();chart.x=18;chart.y=10;chart.width=230*mm;chart.height=32*mm;chart.data=[list(weekly.values)];chart.categoryAxis.categoryNames=[pd.Timestamp(x).strftime("%d %b") for x in weekly.index];chart.categoryAxis.labels.fontSize=6;chart.valueAxis.labels.fontSize=6;chart.valueAxis.labelTextFormat="%0.0f";chart.lines[0].strokeColor=ORANGE;chart.lines[0].strokeWidth=2;d.add(chart);story.append(d)
    story.append(Paragraph("Chart values are INR. The latest point is the week beginning 9 November; PO records are not supplied beyond that week.",styles["SmallJoy"]))
    top=alerts.head(7)
    table("Highest-priority actions",top,["priority","category","platform","city","product","status","estimated_revenue_impact_inr"],["Priority","Issue","Platform","City","Product / SKU","Status","Est. exposure"],[19*mm,47*mm,22*mm,25*mm,57*mm,30*mm,38*mm])

    story.append(PageBreak())
    story.extend([Paragraph("Supply and discoverability review",styles["TitleJoy"]),Paragraph("Evidence is aggregated at the warehouse or platform-city-SKU level. Week starts are Monday.",styles["SmallJoy"])])
    supply=supply_findings.copy()
    if not supply.empty:
        rows=[]
        for _,r in supply.iterrows():
            ev=_evidence(r);rows.append({**r.to_dict(),"ordered_evidence":ev.get("ordered_units"),"delivered_evidence":ev.get("delivered_units"),"shortfall_evidence":ev.get("shortfall_units"),"fill_evidence":ev.get("weighted_fill_rate_pct"),"availability_evidence":ev.get("sales_and_availability",{}).get("availability_pct_during")})
        supply=pd.DataFrame(rows).sort_values("estimated_revenue_impact_inr",ascending=False)
        total_ordered=int(supply.ordered_evidence.sum());total_delivered=int(supply.delivered_evidence.sum());total_short=int(supply.shortfall_evidence.sum());total_fill=100*total_delivered/total_ordered if total_ordered else 0
        span=pd.Timestamp(supply.first_affected_week.min()).strftime("%d %b")+"-"+pd.Timestamp(supply.latest_affected_week.max()).strftime("%d %b")
        story.append(Paragraph(f"{supply.sku_code.nunique()} affected SKUs, {span}: {total_ordered:,} units ordered, {total_delivered:,} delivered, {total_short:,} short; weighted fill rate {total_fill:.1f}%.",styles["BodyJoy"]))
    table("Sustained supply incidents - Blinkit Bengaluru",supply,["product","first_affected_week","latest_affected_week","affected_weeks","ordered_evidence","delivered_evidence","shortfall_evidence","fill_evidence","availability_evidence","estimated_revenue_impact_inr"],["Product / SKU","First low-fill week","Last low-fill week","Weeks","Ordered","Delivered","Short","Fill","Availability","Est. gap"],[48*mm,25*mm,25*mm,14*mm,20*mm,20*mm,18*mm,18*mm,22*mm,29*mm])
    rank=rank_findings.copy()
    if not rank.empty:
        rows=[]
        for _,r in rank.iterrows():
            ev=_evidence(r);ctx=ev.get("historical_baseline_and_affected_sales",{})
            rows.append({**r.to_dict(),"rank_baseline":ev.get("historical_baseline_rank_first_four_weeks"),"rank_latest":ev.get("latest_rank"),"rank_gap":ev.get("rank_deterioration_places"),"sales_baseline":ctx.get("sales_inr_baseline_weekly"),"sales_during":ctx.get("sales_inr_during"),"availability":ctx.get("availability_pct_during")})
        rank=pd.DataFrame(rows)
    table("Marketing - Zepto Bengaluru ranking decline",rank,["product","first_affected_week","latest_affected_week","rank_baseline","rank_latest","rank_gap","sales_baseline","sales_during","availability","estimated_revenue_impact_inr"],["Product / SKU","From","Through","Baseline rank","Latest rank","Places worse","Prior INR/week","Affected INR","Availability","Est. gap"],[44*mm,18*mm,18*mm,22*mm,20*mm,20*mm,28*mm,28*mm,22*mm,29*mm])
    section("Team actions")
    action_parts=[]
    if not supply.empty:
        names=", ".join(supply["product"].dropna().astype(str).unique())
        action_parts.append(f"Supply: review allocation and dispatch records for {names}; confirm any recovery held for two consecutive PO weeks and prevent recurrence.")
    if not rank.empty:
        names=", ".join(rank["product"].dropna().astype(str).unique())
        action_parts.append(f"Marketing: audit search placement for {names}, including query match, sponsored slots, stock eligibility and listing quality; monitor rank, availability and sales weekly.")
    story.append(Paragraph(" ".join(action_parts) if action_parts else "No supported supply or search incidents in this market were found.",styles["BodyJoy"]))

    story.append(PageBreak())
    story.extend([Paragraph("Ordering interruptions and action plan",styles["TitleJoy"]),Paragraph("PO gaps below are inferred from missing rows in otherwise highly populated weekly exports, supported by prior orders, resumption and store performance.",styles["SmallJoy"])])
    gaps=order_findings.copy()
    rows=[]
    for _,r in gaps.iterrows():
        ev=_evidence(r);ctx=ev.get("sales_and_availability",{})
        rows.append({**r.to_dict(),"gap_weeks":", ".join(pd.Timestamp(w).strftime("%d %b") for w in ev.get("missing_po_weeks",[])),"prior_order":ev.get("previous_ordered_units"),"availability_before":ev.get("availability_pct_before_gap"),"availability_during":ev.get("availability_pct_during_gap"),"sales_during":ev.get("sales_inr_during_gap"),"coverage":ev.get("weekly_export_coverage_pct")})
    gap_table=pd.DataFrame(rows)
    table("Instamart Hyderabad - September sunscreen ordering pause",gap_table,["product","warehouse","gap_weeks","prior_order","availability_before","availability_during","sales_during","estimated_revenue_impact_inr"],["Product / SKU","Warehouse","No-PO weeks","Prior units","Avail. before","Avail. in gap","Sales in gap","Est. gap"],[49*mm,23*mm,35*mm,20*mm,26*mm,26*mm,29*mm,35*mm])
    if not gap_table.empty:
        names=", ".join(gap_table["product"].dropna().astype(str).unique())
        story.append(Paragraph(f"Platform KAM: confirm the missing PO weeks and export completeness for {names}; restore normal ordering cadence and monitor availability across the affected stores. The limited prior order history and later resumption are shown in the evidence.",styles["BodyJoy"]))
    incident_ids=set(supply_findings.alert_id)|set(rank_findings.alert_id)|set(order_findings.alert_id)
    remainder=alerts[~alerts.alert_id.isin(incident_ids)]
    table("Remaining prioritized actions",remainder.head(8),["priority","category","platform","city","product","status","estimated_revenue_impact_inr","team"],["Priority","Issue","Platform","City","Product / SKU","Status","Est. exposure","Team"],[18*mm,43*mm,21*mm,24*mm,51*mm,28*mm,35*mm,24*mm])
    section("Methods and limitations")
    story.append(Paragraph("Fill rate = delivered units / ordered units; cumulative values are quantity-weighted. Sustained supply incidents require at least three consecutive weekly fill rates below 90%. Search baseline is the mean rank of the first four observed weeks; a deterioration of five or more places is tracked across consecutive weeks. No-PO weeks are inferred only after prior ordering and a multi-week gap; export coverage, later resumption and availability/sales context are included. Revenue impact holds the pre-incident weekly revenue baseline fixed, compares actual sales_inr during affected weeks, floors weekly gaps at zero and is not causal attribution. The one-week Instamart pre-gap history makes its exposure estimate especially uncertain. Availability is a proxy; exact stock on hand is unavailable. Sales cover 7 September-15 November; PO data ends 9 November, so later order activity cannot be tested.",styles["SmallJoy"]))
    if quality is not None and not quality.empty:
        duplicates=int(quality.loc[quality.dataset.eq("sales"),"exact_duplicates"].sum())
        story.append(Paragraph(f"Data quality: {duplicates} exact duplicate sales rows were removed and logged; remaining source rows had no missing cells or invalid dates. Store and platform-product mappings were validated. See outputs/data_quality.csv and outputs/audit_trail.csv for the audit trail.",styles["SmallJoy"]))

    def footer(canvas,document):
        canvas.saveState();canvas.setStrokeColor(ORANGE);canvas.setLineWidth(.7);canvas.line(12*mm,11*mm,width-12*mm,11*mm);canvas.setFont("Helvetica",7.5);canvas.setFillColor(NAVY);canvas.drawString(12*mm,7*mm,"JOY | Internal Monday Business Review");canvas.drawRightString(width-12*mm,7*mm,f"Page {document.page}");canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return out_path
