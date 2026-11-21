"""Load, normalize and audit supplied exports without filling unknowns with zero."""
import pandas as pd
from pathlib import Path
from config import DATA_DIR, DATA_CUTOFF, OUTPUT_DIR

FILES = {"sales":"daily_sales.csv", "stores":"dark_stores.csv", "products":"products.csv", "orders":"purchase_orders.csv"}
PLATFORM_MAP = {"blinkit":"Blinkit", "zepto":"Zepto", "instamart":"Instamart", "swiggy instamart":"Instamart"}

def load_data(data_dir=DATA_DIR):
    data_dir=Path(data_dir)
    frames={}; audit=[]; trail=[]
    for key,name in FILES.items():
        path=data_dir/name
        if not path.exists():
            raise FileNotFoundError(f"Required input missing: {path}")
        df=pd.read_csv(path,dtype={"platform_product_id":"string"})
        original=len(df); dup=int(df.duplicated().sum())
        if dup:
            df=df.drop_duplicates().copy()
            trail.append(dict(dataset=key,decision="Remove exact duplicate rows",rows_affected=dup,reason="Exact duplicate export rows add no new observation; count retained in data_quality.csv"))
        if "platform" in df:
            before=df.platform.astype(str).copy()
            df["platform"]=df.platform.astype(str).str.strip().str.lower().map(PLATFORM_MAP).fillna(df.platform.astype(str).str.strip())
            changed=int((before != df.platform).sum())
        else: changed=0
        id_fields=[c for c in ["dark_store_id","platform_product_id","warehouse_id","sku_code","po_id"] if c in df]
        id_trimmed=0
        for c in id_fields:
            as_text=df[c].astype("string")
            id_trimmed+=int((as_text.fillna("")!=as_text.str.strip().fillna("")).sum())
            df[c]=as_text.str.strip()
        if id_trimmed: trail.append(dict(dataset=key,decision="Trim surrounding whitespace from identifier fields",rows_affected=id_trimmed,reason="Normalize identifiers before exact joins; source values remain traceable in supplied exports"))
        datecols=[c for c in df.columns if c.endswith("date") or c=="date"]
        bad_dates=0
        for c in datecols:
            parsed=pd.to_datetime(df[c],errors="coerce")
            bad_dates+=int(parsed.isna().sum()); df[c]=parsed
        if bad_dates: trail.append(dict(dataset=key,decision="Exclude records with unparseable dates from period analytics",rows_affected=bad_dates,reason="A record with no valid reporting week cannot be assigned to the requested Monday-Sunday period"))
        audit.append(dict(dataset=key,rows_input=original,exact_duplicates=dup,rows_retained=len(df),platform_names_normalized=changed,invalid_dates=bad_dates,missing_cells=int(df.isna().sum().sum())))
        frames[key]=df
    sales=frames['sales']; cutoff=pd.Timestamp(DATA_CUTOFF)
    frames['sales']=sales[sales.date.le(cutoff)].copy()
    frames['orders']=frames['orders'][frames['orders'].po_date.le(cutoff)].copy()
    # Normalize common city aliases before store and PO analytics.
    city_alias={'bangalore':'Bengaluru','bengaluru':'Bengaluru','hyderabad':'Hyderabad','mumbai':'Mumbai','pune':'Pune','kolkata':'Kolkata','delhi':'Delhi NCR','new delhi':'Delhi NCR','delhi ncr':'Delhi NCR'}
    for key in ['stores']:
        original_city=frames[key].city.astype('string')
        normalized_city=original_city.str.strip().str.lower().map(city_alias).fillna(original_city.str.strip())
        changed=int((original_city.fillna('')!=normalized_city.fillna('')).sum())
        frames[key]['city']=normalized_city
        if changed: trail.append(dict(dataset=key,decision="Normalize city case and common aliases",rows_affected=changed,reason="Use consistent city groups for store, sales and warehouse incident analysis"))
    # Numeric validation is explicit; invalid critical rows are excluded from calculations only after an audit record.
    invalid=[]
    conditions={
      'sales':{'availability_pct':lambda s:s.lt(0)|s.gt(100),'units_sold':lambda s:s.lt(0),'selling_price_inr':lambda s:s.lt(0),'sales_inr':lambda s:s.lt(0),'search_rank':lambda s:s.le(0)},
      'orders':{'qty_ordered':lambda s:s.le(0),'qty_delivered':lambda s:s.lt(0)},
    }
    drop_masks={}
    for key,fields in conditions.items():
        drop_mask=pd.Series(False,index=frames[key].index)
        for c,bad_fn in fields.items():
            frames[key][c]=pd.to_numeric(frames[key][c],errors='coerce')
            bad=frames[key][c].isna()|bad_fn(frames[key][c]); n=int(bad.sum())
            if n:
                invalid.append(dict(dataset=key,field=c,invalid_or_negative=n))
                if key=='sales' and c in ('availability_pct','search_rank','selling_price_inr'):
                    # Preserve otherwise valid sales rows; an unknown signal remains null, never zero.
                    frames[key].loc[bad,c]=pd.NA
                else: drop_mask|=bad
        drop_masks[key]=drop_mask
    for key,mask in drop_masks.items():
        n=int(mask.sum())
        if n:
            trail.append(dict(dataset=key,decision="Exclude rows with invalid critical numeric values",rows_affected=n,reason="Prevent invalid quantities, prices, availability or ranks from contaminating metrics; see invalid_values.csv"))
            frames[key]=frames[key].loc[~mask].copy()
    sales_check=frames['sales'].units_sold*frames['sales'].selling_price_inr
    discrep=int(frames['sales'].sales_inr.ne(sales_check).sum())
    if discrep: invalid.append(dict(dataset='sales',field='sales_inr_vs_units_x_price',invalid_or_negative=discrep))
    frames['sales']=frames['sales'].merge(frames['stores'][['dark_store_id','platform','city','warehouse_id']],on='dark_store_id',how='left',suffixes=('','_store'),indicator='_store_match',validate='many_to_one')
    if 'city' in frames['sales']:
        frames['sales']['city']=frames['sales'].city.astype('string').str.strip().str.lower().map(city_alias).fillna(frames['sales'].city)
    # Preserve source platform, flag store-platform mismatch and attach internal SKU via platform mapping.
    frames['sales']['store_mapping_missing']=frames['sales']['warehouse_id'].isna()
    prod=frames['products'][['platform','platform_product_id','sku_code','product_name','category','pack_size']].drop_duplicates(['platform','platform_product_id'])
    frames['sales']=frames['sales'].merge(prod,on=['platform','platform_product_id'],how='left',indicator='_product_match',validate='many_to_one')
    frames['sales']['product_mapping_missing']=frames['sales']['sku_code'].isna()
    quality=pd.DataFrame(audit)
    extras=pd.DataFrame(invalid,columns=['dataset','field','invalid_or_negative'])
    quality.to_csv(OUTPUT_DIR/'data_quality.csv',index=False)
    extras.to_csv(OUTPUT_DIR/'invalid_values.csv',index=False)
    mappings=pd.DataFrame([
      {'check':'unmapped sales dark stores','count':int(frames['sales'].store_mapping_missing.sum())},
      {'check':'unmapped product platform IDs','count':int(frames['sales'].product_mapping_missing.sum())},
      {'check':'sales platform differs from store platform','count':int((frames['sales'].platform!=frames['sales'].platform_store).sum())},
      {'check':'potential duplicate PO IDs','count':int(frames['orders'].po_id.duplicated().sum())},
      {'check':'duplicate dark_store_id mappings','count':int(frames['stores'].dark_store_id.duplicated().sum())},
      {'check':'duplicate platform product ID mappings','count':int(frames['products'].duplicated(['platform','platform_product_id']).sum())},
      {'check':'missing product mappings for purchase orders','count':int((~frames['orders'].sku_code.isin(frames['products'].sku_code)).sum())},
    ])
    mappings.to_csv(OUTPUT_DIR/'mapping_quality.csv',index=False)
    overdelivery=int((frames['orders'].qty_delivered>frames['orders'].qty_ordered).sum())
    if overdelivery: trail.append(dict(dataset='orders',decision="Flag delivered quantity above ordered quantity",rows_affected=overdelivery,reason="Retained for review; do not cap delivered values or conceal fill rates above 100%"))
    formula_check=frames['sales'].selling_price_inr.notna()&frames['sales'].units_sold.notna()&frames['sales'].sales_inr.notna()
    discrepancy=int((frames['sales'].loc[formula_check,'sales_inr']!=(frames['sales'].loc[formula_check,'units_sold']*frames['sales'].loc[formula_check,'selling_price_inr'])).sum())
    if discrepancy: trail.append(dict(dataset='sales',decision="Flag sales amount inconsistent with units times selling price",rows_affected=discrepancy,reason="Preserve source sales_inr as reported; do not silently replace actual sales values"))
    pd.DataFrame(trail,columns=['dataset','decision','rows_affected','reason']).to_csv(OUTPUT_DIR/'audit_trail.csv',index=False)
    return frames,quality
