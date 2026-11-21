"""Joy Quick Commerce Intelligence Streamlit dashboard."""
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from config import ALERT_LIMIT, DATA_CUTOFF, REPORT_DATE
from data_cleaning import load_data
from analytics import analyze, kpis
from alerts import build_alerts, ordering_gaps

st.set_page_config(page_title="Joy Quick Commerce Intelligence",page_icon="🟠",layout="wide")
st.markdown("""<style>
.stApp{background:#fff;color:#172B4D}.block-container{padding-top:1.3rem;padding-bottom:2rem}
h1,h2,h3{color:#172B4D}.stMetric{border:1px solid #E8EBF0;border-radius:10px;padding:12px;background:#FFF}
[data-testid="stSidebar"]{background:#FBF7F4}
</style>""",unsafe_allow_html=True)
st.title("JOY QUICK COMMERCE INTELLIGENCE")
st.caption(f"Monday Business Review | {pd.Timestamp(REPORT_DATE):%d %B %Y} | Sales through Sunday, {pd.Timestamp(DATA_CUTOFF):%d %B %Y}")

@st.cache_data(show_spinner="Preparing weekly analysis...")
def get_model():
    data,quality=load_data();analysis=analyze(data);alerts=build_alerts(analysis);gaps=ordering_gaps(data)
    return data,quality,analysis,alerts,gaps,kpis(analysis)

try:
    data,quality,a,alerts,gaps,k=get_model()
except Exception as exc:
    st.error(f"Unable to load the supplied datasets: {exc}")
    st.info("Place daily_sales.csv, dark_stores.csv, products.csv and purchase_orders.csv in the data/ folder.")
    st.stop()

pages=["Executive Overview","Supply Chain Intelligence","Sales & Availability","Search & Discoverability","Platform Ordering Gaps","Action Centre"]
page=st.sidebar.radio("Workspace",pages)
st.sidebar.caption("Reporting period: 7 Sep - 15 Nov 2026")
money_fmt="₹%d"

def show_alerts(frame,height=360):
    if frame.empty:
        st.info("No supported findings for these filters in the supplied data.")
        return
    display=[c for c in ["priority","category","platform","city","warehouse","product","sku_code","first_affected_week","latest_affected_week","affected_weeks","status","estimated_revenue_impact_inr","team","score","recommended_action"] if c in frame]
    st.dataframe(frame[display],width="stretch",height=height,hide_index=True,column_config={
      "estimated_revenue_impact_inr":st.column_config.NumberColumn("Estimated exposure (INR)",format="₹%,.0f"),
      "first_affected_week":st.column_config.DateColumn(format="DD MMM YYYY"),
      "latest_affected_week":st.column_config.DateColumn(format="DD MMM YYYY"),
      "score":st.column_config.NumberColumn("Priority score",format="%.1f"),
    })

def evidence_expander(frame):
    if frame.empty:return
    with st.expander("Supporting evidence and calculation assumptions"):
        for r in frame.itertuples(index=False):
            st.markdown(f"**{r.alert_id} | {r.product} | {r.city}**")
            st.json(json.loads(r.supporting_evidence))
            st.caption(r.impact_basis)

if page=="Executive Overview":
    critical=int((alerts.priority=="CRITICAL").sum());high=int((alerts.priority=="HIGH").sum());medium=int((alerts.priority=="MEDIUM").sum())
    metrics=st.columns(4)
    for col,label,value in zip(metrics,["Recorded revenue","Units sold","Products","Platforms"],[f"₹{k['revenue_inr']:,.0f}",f"{k['units_sold']:,}",f"{k['products']}",f"{k['platforms']}"]): col.metric(label,value)
    metrics=st.columns(4)
    for col,label,value in zip(metrics,["Critical alerts","High alerts","Weighted PO fill rate","Latest week revenue gap (est.)"],[str(critical),str(high),f"{k['fill_rate_pct']:.1f}%" if k['fill_rate_pct'] is not None else "N/A",f"₹{k['revenue_at_risk_inr']:,.0f}" if k['revenue_at_risk_inr'] is not None else "N/A"]): col.metric(label,value)
    left,right=st.columns([2,1])
    with left:
        st.subheader("Weekly recorded revenue")
        weekly=a["weekly_sales"].groupby("week_start",as_index=False).revenue_inr.sum()
        fig=px.line(weekly,x="week_start",y="revenue_inr",markers=True,title="Revenue by Monday-Sunday reporting week",labels={"week_start":"Week starting Monday","revenue_inr":"Recorded revenue (INR)"})
        fig.update_traces(line_color="#E85D2A");fig.update_layout(legend_title_text="",yaxis_tickprefix="₹",hovermode="x unified")
        st.plotly_chart(fig,width="stretch")
    with right:
        st.subheader("Alert priorities")
        counts=pd.DataFrame({"Priority":["CRITICAL","HIGH","MEDIUM"],"Alerts":[critical,high,medium]})
        fig=px.bar(counts,x="Priority",y="Alerts",color="Priority",color_discrete_map={"CRITICAL":"#B42318","HIGH":"#E85D2A","MEDIUM":"#E5A000"},title="All flagged incidents")
        fig.update_layout(showlegend=False,xaxis_title="Priority",yaxis_title="Alert count")
        st.plotly_chart(fig,width="stretch")
    st.subheader("Top 15 actions")
    show_alerts(alerts.head(ALERT_LIMIT),height=440)
    st.caption("Exposure amounts are estimates over the incident weeks shown; they are not confirmed lost revenue or current run-rate forecasts.")

elif page=="Supply Chain Intelligence":
    st.subheader("Warehouse fill rate across all observed PO weeks")
    fill=a["warehouse_fill"].sort_values("fill_rate_pct")
    fig=px.bar(fill,x="fill_rate_pct",y="warehouse_id",color="platform",orientation="h",hover_data=["city","ordered_units","delivered_units","shortfall_units"],labels={"fill_rate_pct":"Weighted fill rate (%)","warehouse_id":"Platform warehouse"},title="Cumulative weighted fill rate by warehouse")
    fig.add_vline(x=90,line_dash="dash",line_color="#B42318",annotation_text="90% review threshold")
    st.plotly_chart(fig,width="stretch")
    supply=alerts[alerts.category.isin(["Sustained supply under-delivery","PO shortfall"])].copy()
    st.subheader("Current, resolved and historical supply incidents")
    show_alerts(supply,height=380);evidence_expander(supply)
    st.subheader("Weekly SKU supply detail")
    st.dataframe(a["po_weekly"].sort_values(["platform","warehouse_id","sku_code","week_start"]),width="stretch",hide_index=True,column_config={"fill_rate_pct":st.column_config.NumberColumn(format="%.1f%%"),"week_start":st.column_config.DateColumn(format="DD MMM YYYY")})

elif page=="Sales & Availability":
    st.subheader("Sales trend by platform and city")
    cities=sorted(a["weekly_sales"].city.dropna().unique())
    city=st.selectbox("City",["All cities"]+cities,key="sales_city")
    view=a["weekly_sales"] if city=="All cities" else a["weekly_sales"][a["weekly_sales"].city.eq(city)]
    trend=view.groupby(["week_start","platform"],as_index=False).agg(revenue_inr=("revenue_inr","sum"),units_sold=("units_sold","sum"))
    fig=px.line(trend,x="week_start",y="revenue_inr",color="platform",markers=True,title="Weekly recorded revenue",labels={"week_start":"Week starting Monday","revenue_inr":"Revenue (INR)","platform":"Platform"})
    fig.update_layout(yaxis_tickprefix="₹",hovermode="x unified");st.plotly_chart(fig,width="stretch")
    st.subheader("Latest product performance")
    latest=a["commercial_weekly"].groupby(["platform","city","sku_code","product_name"],as_index=False).tail(1).sort_values("revenue_inr",ascending=False)
    st.dataframe(latest,width="stretch",hide_index=True,column_config={"revenue_inr":st.column_config.NumberColumn(format="₹%,.0f"),"availability_pct":st.column_config.NumberColumn(format="%.1f%%"),"search_rank":st.column_config.NumberColumn("Avg. search rank",format="%.1f")})
    st.caption("Availability is the supplied availability_pct signal. Inventory-on-hand is not present in these exports.")

elif page=="Search & Discoverability":
    st.caption("A lower search rank is better. The historical baseline is the mean rank over the first four observed weeks for each platform-city-SKU.")
    ranking=alerts[alerts.category.eq("Search visibility deterioration")]
    show_alerts(ranking,height=220);evidence_expander(ranking)
    platform=st.selectbox("Platform",sorted(a["commercial_weekly"].platform.unique()),key="rank_platform")
    cities=sorted(a["commercial_weekly"].loc[a["commercial_weekly"].platform.eq(platform),"city"].dropna().unique())
    city=st.selectbox("City",cities,key="rank_city")
    available=a["commercial_weekly"][(a["commercial_weekly"].platform==platform)&(a["commercial_weekly"].city==city)]
    products=available[["sku_code","product_name"]].drop_duplicates().sort_values("product_name")
    sku=st.selectbox("Product",products.sku_code.tolist(),format_func=lambda x:products.set_index('sku_code').loc[x,'product_name'],key="rank_sku")
    series=available[available.sku_code.eq(sku)].sort_values("week_start")
    fig=px.line(series,x="week_start",y="search_rank",markers=True,title="Weekly average search position (lower is better)",labels={"week_start":"Week starting Monday","search_rank":"Average rank"})
    fig.update_yaxes(autorange="reversed",dtick=1);st.plotly_chart(fig,width="stretch")
    fig=px.line(series,x="week_start",y="availability_pct",markers=True,title="Weekly availability signal",labels={"week_start":"Week starting Monday","availability_pct":"Availability (%)"})
    st.plotly_chart(fig,width="stretch")
    st.dataframe(series[["week_start","product_name","search_rank","historical_rank_baseline","rank_vs_baseline","revenue_inr","units_sold","availability_pct"]],width="stretch",hide_index=True,column_config={"week_start":st.column_config.DateColumn(format="DD MMM YYYY"),"revenue_inr":st.column_config.NumberColumn(format="₹%,.0f"),"search_rank":st.column_config.NumberColumn(format="%.2f"),"historical_rank_baseline":st.column_config.NumberColumn(format="%.2f"),"rank_vs_baseline":st.column_config.NumberColumn(format="%+.2f")})

elif page=="Platform Ordering Gaps":
    st.warning("PO data ends 9 November 2026. A missing row is treated as an inferred pause only when prior orders and a multi-week gap are present; completeness and availability evidence are shown.")
    if not gaps.empty:
        gaps_view=gaps.sort_values(["first_missing_week","platform","sku_code"])
        st.dataframe(gaps_view,width="stretch",hide_index=True,column_config={"first_missing_week":st.column_config.DateColumn(format="DD MMM YYYY"),"latest_missing_week":st.column_config.DateColumn(format="DD MMM YYYY")})
        with st.expander("Gap evidence"):
            for r in gaps_view.itertuples(index=False):
                st.markdown(f"**{r.platform} | {r.city} | {r.product}**")
                st.json(json.loads(r.supporting_evidence))
    else:
        st.info("No two-week ordering gaps with supporting history and adequate weekly record coverage were found.")
    order_alerts=alerts[alerts.category.eq("Platform ordering interruption")]
    st.subheader("Prioritized KAM actions");show_alerts(order_alerts)

elif page=="Action Centre":
    st.subheader("Alert filters")
    filtered=alerts.copy()
    cols=st.columns(5)
    for col,key,label in zip(cols,["priority","platform","city","team","status"],["Priority","Platform","City","Responsible team","Status"]):
        values=sorted(filtered[key].dropna().astype(str).unique())
        selected=col.multiselect(label,values,key=f"filter_{key}")
        if selected:filtered=filtered[filtered[key].astype(str).isin(selected)]
    st.subheader(f"{len(filtered)} matching alerts | ranked by score")
    show_alerts(filtered,height=470);evidence_expander(filtered)
    st.download_button("Download filtered alert CSV",filtered.to_csv(index=False),"joy_alerts_filtered.csv","text/csv")
    st.caption("Priority score = 30% severity + 25% revenue impact percentile + 20% duration (capped at 6 weeks) + 15% affected-store footprint + 10% product importance percentile. Critical ≥75; High ≥50; otherwise Medium.")

st.caption("No exact stock-on-hand values are available. Estimated revenue exposure is an assumption-based comparison, not confirmed lost revenue.")
