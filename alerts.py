"""Incident-level alerts with evidence, status and explainable priority scoring."""
from __future__ import annotations
import hashlib
import json
import numpy as np
import pandas as pd
from analytics import consecutive_runs
from config import LOW_FILL_RATE, LOW_AVAILABILITY, SALES_DECLINE_PCT, RANK_DETERIORATION, SUSTAINED_WEEKS, ALERT_SCORE_WEIGHTS, CRITICAL_SCORE, HIGH_SCORE
from config import MIN_ORDER_GAP_WEEKS,MIN_PO_COVERAGE_PCT

ALERT_COLUMNS=["alert_id","priority","category","platform","city","warehouse","product","sku_code","first_affected_week","latest_affected_week","affected_weeks","supporting_evidence","estimated_revenue_impact_inr","impact_basis","team","recommended_action","status","score"]

def _alert_id(category,platform,warehouse,sku,first):
    seed="|".join(map(str,[category,platform,warehouse,sku,pd.Timestamp(first).date()]))
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12].upper()

def _status(last_affected,latest_week):
    days=(pd.Timestamp(latest_week)-pd.Timestamp(last_affected)).days
    return "Current" if days==0 else ("Recently Resolved" if days<=21 else "Historical")

def _baseline_gap(city_rows,affected_weeks,min_prior=2):
    """Hold a pre-incident baseline fixed across the event; None means unsupported."""
    if city_rows.empty: return None,0
    city_rows=city_rows.sort_values("week_start").set_index("week_start")
    weeks=sorted(pd.Timestamp(w) for w in affected_weeks)
    if not weeks: return None,0
    baseline=city_rows.loc[city_rows.index<weeks[0],"revenue_inr"].tail(4)
    if len(baseline)<min_prior: return None,0
    actual=[]
    for week in weeks:
        current=city_rows.loc[city_rows.index==week,"revenue_inr"]
        if not current.empty: actual.append(float(current.iloc[-1]))
    if not actual: return None,0
    gap=sum(max(0.0,float(baseline.mean())-value) for value in actual)
    return int(round(gap)),len(actual)

def _city_rows(a,platform,city,sku):
    df=a["commercial_weekly"]
    return df[(df.platform==platform)&(df.city==city)&(df.sku_code==sku)].copy()

def _sales_context(a,platform,city,sku,weeks):
    rows=_city_rows(a,platform,city,sku).sort_values("week_start")
    affected=set(pd.Timestamp(x) for x in weeks)
    current=rows[rows.week_start.isin(affected)]
    previous=rows[rows.week_start<min(affected)].tail(4)
    return {
      "sales_weeks":int(len(current)),
      "sales_inr_during":int(current.revenue_inr.sum()) if not current.empty else None,
      "sales_inr_baseline_weekly":round(float(previous.revenue_inr.mean()),2) if len(previous)>=1 else None,
      "availability_pct_baseline":round(float(previous.availability_pct.mean()),1) if not previous.empty else None,
      "availability_pct_during":round(float(current.availability_pct.mean()),1) if not current.empty else None,
      "rank_baseline":round(float(previous.search_rank.mean()),2) if not previous.empty else None,
      "rank_during":round(float(current.search_rank.mean()),2) if not current.empty else None,
      "dark_stores_observed":int(current.dark_stores.max()) if not current.empty else 0,
    }

def _record(category,platform,city,warehouse,product,sku,weeks,evidence,impact,basis,team,action,status,latest,severity,stores,importance):
    first=min(pd.Timestamp(w) for w in weeks); last=max(pd.Timestamp(w) for w in weeks)
    return dict(alert_id=_alert_id(category,platform,warehouse,sku,first),priority="MEDIUM",category=category,platform=platform,city=city,warehouse=warehouse or "",product=product or sku,sku_code=sku,first_affected_week=first,latest_affected_week=last,affected_weeks=len(set(weeks)),supporting_evidence=json.dumps(evidence,ensure_ascii=False,sort_keys=True),estimated_revenue_impact_inr=impact,impact_basis=basis,team=team,recommended_action=action,status=status,score=0.0,_severity=float(np.clip(severity,0,1)),_stores=max(0,int(stores)),_importance=max(0,float(importance)))

def _impact_percentiles(records):
    vals=pd.Series([r["estimated_revenue_impact_inr"] if r["estimated_revenue_impact_inr"] is not None else 0 for r in records],dtype=float)
    ranks=vals.rank(pct=True,method="average").fillna(0)
    store_max=max([r["_stores"] for r in records] or [1])
    importance=pd.Series([r["_importance"] for r in records],dtype=float).rank(pct=True,method="average").fillna(0)
    for i,r in enumerate(records):
        revenue_component=float(ranks.iloc[i]);duration=min(r["affected_weeks"]/6,1.0);store_component=r["_stores"]/store_max if store_max else 0
        weights=ALERT_SCORE_WEIGHTS
        score=100*(weights["severity"]*r["_severity"]+weights["revenue"]*revenue_component+weights["duration"]*duration+weights["store_footprint"]*store_component+weights["product_importance"]*float(importance.iloc[i]))
        r["score"]=round(score,1)
        r["priority"]="CRITICAL" if score>=CRITICAL_SCORE else ("HIGH" if score>=HIGH_SCORE else "MEDIUM")
        for private in ("_severity","_stores","_importance"): r.pop(private,None)
    return records

def ordering_gaps(data):
    """Find two-or-more-week missing PO runs after an observed order; never zero-fill."""
    orders=data["orders"].copy(); stores=data["stores"].copy(); products=data["products"].copy()
    orders["week_start"]=orders.po_date.dt.to_period("W-SUN").dt.start_time
    weeks=sorted(orders.week_start.unique())
    if not weeks: return pd.DataFrame()
    coverage=po_weekly_coverage(data)
    week_coverage={pd.Timestamp(r.week_start):float(r.coverage_pct)/100 for r in coverage.itertuples(index=False)}
    wh=stores.groupby(["platform","warehouse_id"],as_index=False).agg(city=("city","first"),first_open=("opened_date","min"),dark_store_count=("dark_store_id","nunique"))
    sku_by_platform=products.groupby("platform").sku_code.unique().to_dict()
    for week in weeks:
        obs=orders.loc[orders.week_start.eq(week),["platform","warehouse_id","sku_code"]].drop_duplicates()
        expected=0
        for _,wrow in wh.iterrows():
            active=pd.Timestamp(wrow.first_open)<=pd.Timestamp(week)+pd.Timedelta(days=6)
            if active: expected+=len(sku_by_platform.get(wrow.platform,[]))
        if pd.Timestamp(week) not in week_coverage: week_coverage[pd.Timestamp(week)]=len(obs)/expected if expected else np.nan
    actual=orders.groupby(["platform","warehouse_id","sku_code","week_start"]).qty_ordered.sum()
    name=products.drop_duplicates("sku_code").set_index("sku_code").product_name.to_dict()
    rows=[]
    full_weeks=[pd.Timestamp(w) for w in weeks]
    for _,warehouse in wh.iterrows():
        platform=warehouse.platform;warehouse_id=warehouse.warehouse_id
        active_weeks=[w for w in full_weeks if pd.Timestamp(warehouse.first_open)<=w+pd.Timedelta(days=6)]
        for sku in sku_by_platform.get(platform,[]):
            series=pd.Series(index=active_weeks,dtype=float)
            for w in active_weeks:
                key=(platform,warehouse_id,sku,w)
                series.loc[w]=actual.get(key,np.nan)
            missing=series.isna()
            run_frame=pd.DataFrame({"week_start":series.index,"missing":missing.to_numpy()})
            for run in consecutive_runs(run_frame,run_frame.missing):
                gap_weeks=list(pd.to_datetime(run.week_start))
                if len(gap_weeks)<MIN_ORDER_GAP_WEEKS: continue
                start=gap_weeks[0];end=gap_weeks[-1]
                prior=series.loc[series.index<start].dropna();future=series.loc[series.index>end].dropna()
                if prior.empty: continue
                resume=not future.empty
                # One observed prior order plus a two-week gap, recovery, and corroborating store deterioration
                # is enough to report an inferred interruption; a SKU with no order history is never flagged.
                city=warehouse.city
                sales=data.get("sales")
                context=None
                if sales is not None:
                    s=sales[(sales.platform==platform)&(sales.city==city)&(sales.sku_code==sku)].copy()
                    s["week_start"]=s.date.dt.to_period("W-SUN").dt.start_time
                    ctx=s[s.week_start.isin(gap_weeks)]
                    prev=s[s.week_start<start]
                    availability=float(ctx.availability_pct.mean()) if not ctx.empty else np.nan
                    previous_availability=float(prev.availability_pct.mean()) if not prev.empty else np.nan
                    revenue=float(ctx.sales_inr.sum()) if not ctx.empty else np.nan
                    previous_revenue=float(prev.groupby("week_start").sales_inr.sum().tail(4).mean()) if not prev.empty else np.nan
                    context={"observed_po_weeks_before_gap":int(len(prior)),"previous_ordered_units":int(prior.iloc[-1]),"resumed_after_gap":resume,"order_export_coverage_by_gap_week":{str(w.date()):round(week_coverage.get(w,np.nan),4) for w in gap_weeks},"sales_inr_during_gap":int(revenue) if pd.notna(revenue) else None,"prior_weekly_sales_inr_baseline":round(previous_revenue,2) if pd.notna(previous_revenue) else None,"availability_pct_during_gap":round(availability,1) if pd.notna(availability) else None,"availability_pct_before_gap":round(previous_availability,1) if pd.notna(previous_availability) else None}
                    baseline_total=(previous_revenue*len(gap_weeks)) if pd.notna(previous_revenue) else np.nan
                    sales_drop=(pd.notna(baseline_total) and baseline_total>0 and revenue<=baseline_total*0.5)
                    supported=resume or (pd.notna(availability) and availability<20 and sales_drop)
                    if not supported: continue
                else:
                    context={"observed_po_weeks_before_gap":int(len(prior)),"resumed_after_gap":resume}
                    if not resume: continue
                coverage=min(week_coverage.get(w,0) for w in gap_weeks)
                if coverage<MIN_PO_COVERAGE_PCT/100: continue
                rows.append(dict(platform=platform,warehouse=warehouse_id,city=city,sku_code=sku,product=name.get(sku,sku),first_missing_week=start,latest_missing_week=end,consecutive_missing_weeks=len(gap_weeks),prior_order_weeks=int(len(prior)),prior_ordered_units=int(prior.sum()),following_order_units=int(future.iloc[0]) if resume else None,resumed_after_gap=resume,store_count=int(warehouse.dark_store_count),supporting_evidence=json.dumps(context,ensure_ascii=False,sort_keys=True),export_coverage_pct=round(coverage*100,1)))
    return pd.DataFrame(rows)

def po_weekly_coverage(data):
    """Compare observed warehouse-SKU PO combinations with active expected combinations."""
    orders=data["orders"].copy();stores=data["stores"].copy();products=data["products"].copy()
    orders["week_start"]=orders.po_date.dt.to_period("W-SUN").dt.start_time
    warehouses=stores.groupby(["platform","warehouse_id"],as_index=False).agg(first_open=("opened_date","min"))
    skus=products.groupby("platform").sku_code.nunique().to_dict()
    rows=[]
    for week,group in orders.groupby("week_start"):
        expected=sum(int(skus.get(w.platform,0)) for w in warehouses.itertuples(index=False) if pd.Timestamp(w.first_open)<=pd.Timestamp(week)+pd.Timedelta(days=6))
        observed=int(group[["platform","warehouse_id","sku_code"]].drop_duplicates().shape[0])
        rows.append(dict(week_start=pd.Timestamp(week),observed_combinations=observed,expected_combinations=expected,coverage_pct=round(100*observed/expected,2) if expected else np.nan))
    return pd.DataFrame(rows).sort_values("week_start").reset_index(drop=True)

def build_alerts(a):
    records=[];covered=set();latest=pd.Timestamp(a["commercial_weekly"].week_start.max());po=a["po_weekly"]
    # Sustained and current supply incidents, one record per warehouse/SKU episode.
    lowfill=po.fill_rate_pct.lt(LOW_FILL_RATE)&po.shortfall_units.gt(0)
    product_importance=a["commercial_weekly"].groupby("sku_code").revenue_inr.mean().to_dict()
    for key,group in po.groupby(["platform","city","warehouse_id","sku_code","product_name"],dropna=False):
        platform,city,warehouse,sku,product=key;group=group.sort_values("week_start").copy()
        runs=consecutive_runs(group,group.fill_rate_pct.lt(LOW_FILL_RATE)&group.shortfall_units.gt(0))
        substantial=[r for r in runs if len(r)>=SUSTAINED_WEEKS]
        # Include each sustained episode, even after recovery; exact weeks and totals stay visible.
        for run in substantial:
            weeks=list(pd.to_datetime(run.week_start));fill=float(run.delivered_units.sum()/run.ordered_units.sum()*100)
            metrics=_sales_context(a,platform,city,sku,weeks);impact,usable=_baseline_gap(_city_rows(a,platform,city,sku),weeks,min_prior=2)
            evidence={"weekly_fill_rate_pct":{str(pd.Timestamp(r.week_start).date()):round(float(r.fill_rate_pct),1) for _,r in run.iterrows()},"ordered_units":int(run.ordered_units.sum()),"delivered_units":int(run.delivered_units.sum()),"shortfall_units":int(run.shortfall_units.sum()),"weighted_fill_rate_pct":round(fill,1),"sales_and_availability":metrics,"revenue_gap_weeks_with_baseline":usable}
            last=weeks[-1]; status=_status(last,latest)
            action=(f"Current: recover {int(run.shortfall_units.sum()):,} cumulative short units; agree next-cycle allocation with the platform and reconcile dispatch versus receipt." if status=="Current" else f"Review the {int(run.shortfall_units.sum()):,}-unit historical shortfall with supply planning; confirm corrective allocation is holding at 90% fill or better for two consecutive POs.")
            records.append(_record("Sustained supply under-delivery",platform,city,warehouse,product,sku,weeks,evidence,impact,"Estimated city-SKU sales gap during under-fill weeks versus preceding observed weekly revenue baseline (at least two prior weeks); not causal lost revenue.","Supply",action,status,latest,min(1,(90-fill)/60),metrics["dark_stores_observed"],product_importance.get(sku,0)))
            covered.update((platform,city,sku,w) for w in weeks)
        # Latest one-week supply issue if not already represented by a sustained run.
        lastrow=group.iloc[-1]
        lastweek=pd.Timestamp(lastrow.week_start)
        if bool(lastrow.fill_rate_pct<LOW_FILL_RATE) and not any(lastweek in set(pd.to_datetime(r.week_start)) for r in substantial):
            metrics=_sales_context(a,platform,city,sku,[lastweek]);impact,usable=_baseline_gap(_city_rows(a,platform,city,sku),[lastweek],min_prior=2)
            evidence={"ordered_units":int(lastrow.ordered_units),"delivered_units":int(lastrow.delivered_units),"shortfall_units":int(lastrow.shortfall_units),"fill_rate_pct":round(float(lastrow.fill_rate_pct),1),"sales_and_availability":metrics,"revenue_gap_weeks_with_baseline":usable}
            records.append(_record("PO shortfall",platform,city,warehouse,product,sku,[lastweek],evidence,impact,"Estimated latest-week city-SKU sales gap versus preceding observed baseline; shortfall units themselves are not asserted to be lost retail sales.","Supply",f"Confirm allocation and delivery for {int(lastrow.shortfall_units)} short units; reconcile supplier dispatch and warehouse receipt.",_status(lastweek,latest),latest,min(1,(90-float(lastrow.fill_rate_pct))/60),metrics["dark_stores_observed"],product_importance.get(sku,0)))
            covered.add((platform,city,sku,lastweek))
    # Historical-to-current search visibility collapse versus each SKU's first four observed weeks.
    trend=a["commercial_weekly"]
    for key,group in trend.groupby(["platform","city","sku_code","product_name"],dropna=False):
        platform,city,sku,product=key;group=group.sort_values("week_start").copy()
        baseline=float(group.historical_rank_baseline.iloc[0]);bad=group.rank_vs_baseline.ge(RANK_DETERIORATION)
        runs=consecutive_runs(group,bad)
        for run in runs:
            if len(run)<2 and (float(run.rank_vs_baseline.max())<8): continue
            weeks=list(pd.to_datetime(run.week_start));latest_rank=float(run.search_rank.iloc[-1]);rank_gap=latest_rank-baseline
            metrics=_sales_context(a,platform,city,sku,weeks);impact,usable=_baseline_gap(_city_rows(a,platform,city,sku),weeks,min_prior=2)
            evidence={"historical_baseline_rank_first_four_weeks":round(baseline,2),"weekly_rank":{str(pd.Timestamp(r.week_start).date()):round(float(r.search_rank),2) for _,r in run.iterrows()},"latest_rank":round(latest_rank,2),"rank_deterioration_places":round(rank_gap,2),"historical_baseline_and_affected_sales":metrics,"revenue_gap_weeks_with_baseline":usable,"availability_is_proxy_not_inventory":True}
            status=_status(weeks[-1],latest)
            records.append(_record("Search visibility deterioration",platform,city,"",product,sku,weeks,evidence,impact,"Estimated revenue gap during flagged ranking weeks versus preceding observed sales baseline; correlation only, not causal attribution.","Marketing","Audit search placement and query match; review sponsored placement, stock eligibility, title/images and listing quality. Track rank, availability and sales weekly.",status,latest,min(1,rank_gap/10),metrics["dark_stores_observed"],product_importance.get(sku,0)))
            covered.update((platform,city,sku,w) for w in weeks)
    # Ordering pauses: require observed previous orders and a multi-week absence; never treat a missing row as a numeric zero.
    orders=a["orders"].copy();orders["week_start"]=orders.po_date.dt.to_period("W-SUN").dt.start_time
    all_weeks=sorted(pd.Timestamp(x) for x in orders.week_start.unique())
    store_dim=a["stores"].groupby(["platform","warehouse_id"],as_index=False).agg(city=("city","first"),store_count=("dark_store_id","nunique"))
    pnames=a["products"].drop_duplicates("sku_code").set_index("sku_code").product_name.to_dict()
    for gap in ordering_gaps({"orders":orders,"stores":a["stores"],"products":a["products"],"sales":a["sales"]}).itertuples(index=False):
        weeks=list(pd.date_range(gap.first_missing_week,gap.latest_missing_week,freq="7D"));metrics=_sales_context(a,gap.platform,gap.city,gap.sku_code,weeks)
        detail=json.loads(gap.supporting_evidence);impact,usable=_baseline_gap(_city_rows(a,gap.platform,gap.city,gap.sku_code),weeks,min_prior=1)
        evidence={**detail,"missing_po_weeks":[str(pd.Timestamp(w).date()) for w in weeks],"weekly_export_coverage_pct":gap.export_coverage_pct,"estimated_revenue_gap_weeks_with_baseline":usable,"sales_and_availability":metrics,"classification":"Inferred interruption: no PO rows in a near-complete export; confirm platform intent and feed completeness"}
        last=weeks[-1];status=_status(last,latest)
        action=f"Ask the Instamart KAM whether {gap.product} was intentionally paused; confirm September PO feed completeness, restore ordering, and monitor availability at {metrics['dark_stores_observed']} Hyderabad stores."
        records.append(_record("Platform ordering interruption",gap.platform,gap.city,gap.warehouse,gap.product,gap.sku_code,weeks,evidence,impact,"Estimated exposure from preceding weekly observed sales baseline (one prior week available) less actual sales during the two no-PO weeks; estimate only.","Platform KAM",action,status,latest,min(1,gap.consecutive_missing_weeks/2),metrics["dark_stores_observed"],product_importance.get(gap.sku_code,0)))
        covered.update((gap.platform,gap.city,gap.sku_code,w) for w in weeks)
    # Independent latest-week commercial declines/availability. Suppress symptoms already covered by an incident.
    latest_rows=trend[trend.week_start.eq(latest)]
    for r in latest_rows.itertuples(index=False):
        key=(r.platform,r.city,r.sku_code,pd.Timestamp(r.week_start))
        if key in covered: continue
        revenue_drop=pd.notna(r.revenue_change_pct) and r.revenue_change_pct<=SALES_DECLINE_PCT
        availability_low=pd.notna(r.availability_pct) and r.availability_pct<LOW_AVAILABILITY
        if revenue_drop or availability_low:
            weeks=[pd.Timestamp(r.week_start)];impact=int(r.estimated_revenue_gap_inr) if revenue_drop and pd.notna(r.estimated_revenue_gap_inr) else None
            context=_sales_context(a,r.platform,r.city,r.sku_code,weeks)
            category="Sales and availability deterioration" if revenue_drop and availability_low else ("Unexplained sales deterioration" if revenue_drop else "Low availability signal")
            evidence={"week_on_week_revenue_change_pct":round(float(r.revenue_change_pct),1) if pd.notna(r.revenue_change_pct) else None,"revenue_inr":int(r.revenue_inr),"availability_pct":round(float(r.availability_pct),1) if pd.notna(r.availability_pct) else None,"sales_and_availability":context}
            if availability_low:
                team="Operations";action="Validate the availability feed and listing eligibility, then check replenishment status and the platform price/promotion for affected stores."
            else:
                team="Category / Commercial";action="Check promotion, price, listing status and store execution; compare the affected SKU with category and platform peers."
            severity=max(min(1,abs(float(r.revenue_change_pct))/100) if revenue_drop else 0,min(1,(LOW_AVAILABILITY-float(r.availability_pct))/LOW_AVAILABILITY) if availability_low else 0)
            records.append(_record(category,r.platform,r.city,"",r.product_name,r.sku_code,weeks,evidence,impact,"Latest-week revenue compares with the preceding four observed weekly periods; availability is an observed proxy. Neither signal proves causality.",team,action,_status(weeks[0],latest),latest,severity,context["dark_stores_observed"],product_importance.get(r.sku_code,0)))
    if not records: return pd.DataFrame(columns=ALERT_COLUMNS)
    records=_impact_percentiles(records);df=pd.DataFrame(records)
    df=df.sort_values(["score","estimated_revenue_impact_inr","alert_id"],ascending=[False,False,True],na_position="last").drop_duplicates("alert_id")
    df["executive_rank"]=range(1,len(df)+1)
    return df[ALERT_COLUMNS+['executive_rank']].reset_index(drop=True)
