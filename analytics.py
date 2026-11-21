"""Weekly sales, availability, ranking and purchase-order analytics."""
import numpy as np
import pandas as pd
from config import DATA_CUTOFF

def monday_week(values):
    """Return Monday anchors for Monday-Sunday reporting weeks."""
    return pd.to_datetime(values).dt.to_period("W-SUN").dt.start_time

def consecutive_runs(frame, mask, date_col="week_start"):
    """Split selected weekly rows into runs; missing source weeks break a run."""
    selected=frame.loc[mask].sort_values(date_col)
    if selected.empty: return []
    runs=[]; current=[]; previous=None
    for idx,row in selected.iterrows():
        week=pd.Timestamp(row[date_col])
        if previous is not None and (week-previous).days != 7:
            runs.append(selected.loc[current]); current=[]
        current.append(idx); previous=week
    if current: runs.append(selected.loc[current])
    return runs

def safe_pct(numerator, denominator):
    """Division helper returning NaN for missing/zero denominators."""
    denominator=pd.Series(denominator)
    numerator=pd.Series(numerator,index=denominator.index)
    return (100*numerator/denominator.where(denominator.ne(0))).replace([np.inf,-np.inf],np.nan)

def analyze(data):
    sales=data["sales"].copy(); orders=data["orders"].copy()
    sales["week_start"]=monday_week(sales.date)
    orders["week_start"]=monday_week(orders.po_date)
    po_keys=["platform","warehouse_id","sku_code","week_start"]
    po=orders.groupby(po_keys,dropna=False).agg(ordered_units=("qty_ordered","sum"),delivered_units=("qty_delivered","sum"),po_count=("po_id","nunique")).reset_index()
    po["shortfall_units"]=(po.ordered_units-po.delivered_units).clip(lower=0)
    po["fill_rate_pct"]=safe_pct(po.delivered_units,po.ordered_units)
    names=data["products"][["sku_code","product_name","category","pack_size"]].drop_duplicates("sku_code")
    po=po.merge(names,on="sku_code",how="left",validate="many_to_one")
    whdim=data["stores"].groupby(["platform","warehouse_id"],as_index=False).agg(city=("city","first"),dark_store_count=("dark_store_id","nunique"),first_store_open=("opened_date","min"))
    po=po.merge(whdim,on=["platform","warehouse_id"],how="left",validate="many_to_one")
    warehouse_fill=po.groupby(["platform","warehouse_id","city"],dropna=False).agg(ordered_units=("ordered_units","sum"),delivered_units=("delivered_units","sum"),shortfall_units=("shortfall_units","sum")).reset_index()
    warehouse_fill["fill_rate_pct"]=safe_pct(warehouse_fill.delivered_units,warehouse_fill.ordered_units)
    weekly_sales=sales.groupby(["week_start","platform","city"],dropna=False).agg(revenue_inr=("sales_inr","sum"),units_sold=("units_sold","sum"),availability_pct=("availability_pct","mean"),dark_stores=("dark_store_id","nunique")).reset_index().sort_values("week_start")
    store_dims=["platform","city","dark_store_id","sku_code","product_name","category"]
    store_week=sales.groupby(store_dims+["week_start"],dropna=False).agg(revenue_inr=("sales_inr","sum"),units_sold=("units_sold","sum"),availability_pct=("availability_pct","mean"),search_rank=("search_rank","mean")).reset_index().sort_values("week_start")
    store_week["previous_revenue_inr"]=store_week.groupby(store_dims,dropna=False).revenue_inr.shift(1)
    store_week["previous_availability_pct"]=store_week.groupby(store_dims,dropna=False).availability_pct.shift(1)
    store_week["previous_search_rank"]=store_week.groupby(store_dims,dropna=False).search_rank.shift(1)
    store_week["revenue_change_pct"]=safe_pct(store_week.revenue_inr-store_week.previous_revenue_inr,store_week.previous_revenue_inr)
    store_week["rank_change"]=store_week.search_rank-store_week.previous_search_rank
    store_week["revenue_4wk_baseline"]=store_week.groupby(store_dims,dropna=False).revenue_inr.transform(lambda s:s.shift(1).rolling(4,min_periods=2).mean())
    store_week["estimated_revenue_gap_inr"]=(store_week.revenue_4wk_baseline-store_week.revenue_inr).clip(lower=0)
    city_dims=["platform","city","sku_code","product_name","category"]
    commercial=sales.groupby(city_dims+["week_start"],dropna=False).agg(revenue_inr=("sales_inr","sum"),units_sold=("units_sold","sum"),availability_pct=("availability_pct","mean"),search_rank=("search_rank","mean"),dark_stores=("dark_store_id","nunique")).reset_index().sort_values("week_start")
    commercial["previous_revenue_inr"]=commercial.groupby(city_dims,dropna=False).revenue_inr.shift(1)
    commercial["revenue_change_pct"]=safe_pct(commercial.revenue_inr-commercial.previous_revenue_inr,commercial.previous_revenue_inr)
    commercial["previous_search_rank"]=commercial.groupby(city_dims,dropna=False).search_rank.shift(1)
    commercial["rank_change"]=commercial.search_rank-commercial.previous_search_rank
    commercial["historical_rank_baseline"]=commercial.groupby(city_dims,dropna=False).search_rank.transform(lambda s:s.iloc[:min(4,len(s))].mean())
    commercial["rank_vs_baseline"]=commercial.search_rank-commercial.historical_rank_baseline
    commercial["revenue_4wk_baseline"]=commercial.groupby(city_dims,dropna=False).revenue_inr.transform(lambda s:s.shift(1).rolling(4,min_periods=2).mean())
    commercial["estimated_revenue_gap_inr"]=(commercial.revenue_4wk_baseline-commercial.revenue_inr).clip(lower=0)
    return {"sales":sales,"orders":orders,"stores":data["stores"],"products":data["products"],"po_weekly":po,"warehouse_fill":warehouse_fill,"weekly_sales":weekly_sales,"product_weekly":store_week,"commercial_weekly":commercial,"ranking_available":bool(sales.search_rank.notna().any())}

def kpis(a):
    sales=a["sales"]; orders=a["orders"]
    ordered=orders.qty_ordered.sum(min_count=1); delivered=orders.qty_delivered.sum(min_count=1)
    latest=a["commercial_weekly"].week_start.max()
    exposure=a["commercial_weekly"].loc[a["commercial_weekly"].week_start.eq(latest),"estimated_revenue_gap_inr"].sum(min_count=1)
    fill=None if pd.isna(ordered) or ordered==0 or pd.isna(delivered) else float(delivered/ordered*100)
    return {"revenue_inr":int(sales.sales_inr.sum()),"units_sold":int(sales.units_sold.sum()),"products":int(sales.sku_code.nunique()),"platforms":int(sales.platform.nunique()),"fill_rate_pct":fill,"revenue_at_risk_inr":None if pd.isna(exposure) else int(exposure)}
