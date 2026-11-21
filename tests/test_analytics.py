"""Unit and data-backed regression tests for the analytical rules."""
import tempfile
import unittest
from pathlib import Path
import pandas as pd
from analytics import analyze,safe_pct
from alerts import _baseline_gap,build_alerts,ordering_gaps
from data_cleaning import load_data

def synthetic_data():
    weeks=pd.date_range('2026-09-07',periods=8,freq='7D')
    platforms=[('Blinkit','BLK-WH-01','Bengaluru','BLK-STORE'),('Zepto','ZEP-WH-07','Bengaluru','ZEP-STORE'),('Instamart','IM-WH-16','Hyderabad','IM-STORE')]
    specials={'Blinkit':'BLK-SUPPLY','Zepto':'ZEP-FACE','Instamart':'IM-SUN'}
    products=[];stores=[];sales=[];orders=[]
    for platform,warehouse,city,store in platforms:
        stores.append(dict(dark_store_id=store,platform=platform,city=city,warehouse_id=warehouse,opened_date=pd.Timestamp('2025-01-01')))
        for i in range(15):
            sku=specials[platform] if i==0 else f'{platform[:2].upper()}-SKU-{i:02d}'
            category='Face Wash' if sku=='ZEP-FACE' else ('Sunscreen' if sku=='IM-SUN' else 'Lotion')
            products.append(dict(platform=platform,platform_product_id=f'{i+1:04d}',sku_code=sku,product_name=f'Product {sku}',category=category,pack_size='50ml'))
            for j,week in enumerate(weeks):
                rank=3 if sku=='ZEP-FACE' and j<4 else (13 if sku=='ZEP-FACE' else 4)
                avail=90; revenue=1000; units=10
                if sku=='BLK-SUPPLY' and 1<=j<=6: avail=40;revenue=500;units=5
                if sku=='ZEP-FACE' and j>=4:revenue=500;units=5
                if sku=='IM-SUN' and j==1:avail=60;revenue=600;units=6
                if sku=='IM-SUN' and j==2:avail=0;revenue=0;units=0
                sales.append(dict(date=week,platform=platform,dark_store_id=store,warehouse_id=warehouse,city=city,platform_product_id=f'{i+1:04d}',sku_code=sku,product_name=f'Product {sku}',category=category,availability_pct=avail,units_sold=units,selling_price_inr=100,sales_inr=revenue,search_rank=rank))
                missing=sku=='IM-SUN' and j in (1,2)
                if not missing:
                    delivered=50 if sku=='BLK-SUPPLY' and 1<=j<=6 else 100
                    orders.append(dict(po_id=f'{platform}-{sku}-{j}',po_date=week,platform=platform,warehouse_id=warehouse,sku_code=sku,qty_ordered=100,qty_delivered=delivered,delivery_date=week+pd.Timedelta(days=3)))
    return {'sales':pd.DataFrame(sales),'stores':pd.DataFrame(stores),'products':pd.DataFrame(products),'orders':pd.DataFrame(orders)}

class FormulaTests(unittest.TestCase):
    def test_weighted_fill_rate_and_shortfall(self):
        data=synthetic_data(); a=analyze(data)
        row=a['po_weekly'][(a['po_weekly'].platform=='Blinkit')&(a['po_weekly'].sku_code=='BLK-SUPPLY')&(a['po_weekly'].week_start==pd.Timestamp('2026-09-14'))].iloc[0]
        self.assertEqual(row.ordered_units,100);self.assertEqual(row.delivered_units,50);self.assertEqual(row.shortfall_units,50);self.assertEqual(row.fill_rate_pct,50)
    def test_safe_division_by_zero_is_missing(self):
        self.assertTrue(pd.isna(safe_pct(pd.Series([0]),pd.Series([0])).iloc[0]))
    def test_revenue_gap_uses_fixed_preincident_baseline(self):
        weeks=pd.date_range('2026-09-07',periods=4,freq='7D')
        rows=pd.DataFrame({'week_start':weeks,'revenue_inr':[100,200,60,50]})
        gap,count=_baseline_gap(rows,weeks[2:],min_prior=2)
        self.assertEqual(gap,190);self.assertEqual(count,2)
    def test_insufficient_baseline_is_not_zero(self):
        rows=pd.DataFrame({'week_start':pd.to_datetime(['2026-09-07','2026-09-14']),'revenue_inr':[100,0]})
        self.assertEqual(_baseline_gap(rows,[pd.Timestamp('2026-09-14')],min_prior=2),(None,0))

class IncidentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=synthetic_data();cls.analysis=analyze(cls.data);cls.alerts=build_alerts(cls.analysis)
    def test_historical_sustained_fill_incident(self):
        row=self.alerts[self.alerts.category.eq('Sustained supply under-delivery')].iloc[0]
        self.assertEqual(row.affected_weeks,6);self.assertEqual(row.status,'Recently Resolved')
    def test_historical_baseline_search_collapse(self):
        row=self.alerts[self.alerts.category.eq('Search visibility deterioration')].iloc[0]
        ev=__import__('json').loads(row.supporting_evidence)
        self.assertEqual(row.affected_weeks,4);self.assertGreater(ev['rank_deterioration_places'],8)
    def test_missing_purchase_orders_require_prior_history_and_two_weeks(self):
        gaps=ordering_gaps(self.data)
        row=gaps[(gaps.platform=='Instamart')&(gaps.sku_code=='IM-SUN')].iloc[0]
        self.assertEqual(row.consecutive_missing_weeks,2);self.assertTrue(row.resumed_after_gap)
        self.assertEqual(len(gaps),1)
    def test_alert_ids_are_unique(self):
        self.assertEqual(len(self.alerts.alert_id),self.alerts.alert_id.nunique())
    def test_monday_week_boundaries(self):
        a=analyze(synthetic_data())
        self.assertEqual(a['weekly_sales'].week_start.min(),pd.Timestamp('2026-09-07'))
        self.assertTrue((a['po_weekly'].week_start.dt.weekday==0).all())

class CleaningTests(unittest.TestCase):
    def test_platform_product_store_mapping_and_city_normalization(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            pd.DataFrame([{'date':'2026-09-07','platform':'SWIGGY INSTAMART','dark_store_id':'S1','platform_product_id':'001','availability_pct':90,'units_sold':1,'selling_price_inr':100,'sales_inr':100,'search_rank':1}]).to_csv(p/'daily_sales.csv',index=False)
            pd.DataFrame([{'dark_store_id':'S1','platform':'Swiggy Instamart','city':'BANGALORE','pincode':560001,'warehouse_id':'IWH','opened_date':'2025-01-01'}]).to_csv(p/'dark_stores.csv',index=False)
            pd.DataFrame([{'platform':'Instamart','platform_product_id':'001','sku_code':'JOY-1','product_name':'Joy One','category':'Face Wash','pack_size':'50ml','mrp_inr':100}]).to_csv(p/'products.csv',index=False)
            pd.DataFrame([{'po_id':'P1','po_date':'2026-09-07','platform':'Swiggy Instamart','warehouse_id':'IWH','sku_code':'JOY-1','qty_ordered':10,'qty_delivered':8,'delivery_date':'2026-09-10'}]).to_csv(p/'purchase_orders.csv',index=False)
            data,_=load_data(p);row=data['sales'].iloc[0]
            self.assertEqual(row.sku_code,'JOY-1');self.assertEqual(row.platform,'Instamart');self.assertEqual(row.city,'Bengaluru');self.assertFalse(row.product_mapping_missing);self.assertFalse(row.store_mapping_missing)
    def test_missing_values_are_flagged_not_filled_as_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            pd.DataFrame([{'date':'2026-09-07','platform':'Blinkit','dark_store_id':'B1','platform_product_id':'1','availability_pct':90,'units_sold':1,'selling_price_inr':100,'sales_inr':100,'search_rank':1},{'date':'2026-09-08','platform':'Blinkit','dark_store_id':'B1','platform_product_id':'1','availability_pct':90,'units_sold':None,'selling_price_inr':100,'sales_inr':100,'search_rank':1}]).to_csv(p/'daily_sales.csv',index=False)
            pd.DataFrame([{'dark_store_id':'B1','platform':'Blinkit','city':'Bengaluru','pincode':560001,'warehouse_id':'BWH','opened_date':'2025-01-01'}]).to_csv(p/'dark_stores.csv',index=False)
            pd.DataFrame([{'platform':'Blinkit','platform_product_id':'1','sku_code':'JOY-1','product_name':'Joy One','category':'Cream','pack_size':'50ml','mrp_inr':100}]).to_csv(p/'products.csv',index=False)
            pd.DataFrame([{'po_id':'P1','po_date':'2026-09-07','platform':'Blinkit','warehouse_id':'BWH','sku_code':'JOY-1','qty_ordered':10,'qty_delivered':8,'delivery_date':'2026-09-10'}]).to_csv(p/'purchase_orders.csv',index=False)
            data,quality=load_data(p)
            self.assertEqual(len(data['sales']),1)
            audit=pd.read_csv(Path(__file__).parents[1]/'outputs'/'audit_trail.csv')
            self.assertTrue(audit.decision.str.contains('invalid critical numeric').any())
            self.assertEqual(int(quality.loc[quality.dataset.eq('sales'),'missing_cells'].iloc[0]),1)

class SuppliedDataRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).parents[1];cls.data,cls.quality=load_data(root/'data');cls.analysis=analyze(cls.data);cls.alerts=build_alerts(cls.analysis)
    def test_six_blinkit_bengaluru_skus_had_sustained_fill_failure(self):
        x=self.alerts[(self.alerts.category=='Sustained supply under-delivery')&(self.alerts.platform=='Blinkit')&(self.alerts.city=='Bengaluru')]
        self.assertEqual(len(x),6);self.assertTrue((x.affected_weeks==6).all());self.assertTrue((x.status=='Recently Resolved').all())
        evidence=[__import__('json').loads(v) for v in x.supporting_evidence]
        self.assertEqual(sum(e['ordered_units'] for e in evidence),5820);self.assertEqual(sum(e['delivered_units'] for e in evidence),3042);self.assertEqual(sum(e['shortfall_units'] for e in evidence),2778)
    def test_zepto_bengaluru_neem_100_rank_collapse(self):
        x=self.alerts[(self.alerts.category=='Search visibility deterioration')&(self.alerts.platform=='Zepto')&(self.alerts.city=='Bengaluru')&(self.alerts.sku_code=='JY-FW-NEEM-100')]
        self.assertEqual(len(x),1);self.assertEqual(x.iloc[0].latest_affected_week,pd.Timestamp('2026-11-09'))
        ev=__import__('json').loads(x.iloc[0].supporting_evidence);self.assertAlmostEqual(ev['historical_baseline_rank_first_four_weeks'],2.97,places=2);self.assertAlmostEqual(ev['latest_rank'],13.25,places=2)
        ctx=ev['historical_baseline_and_affected_sales'];self.assertAlmostEqual(ctx['availability_pct_baseline'],91.8,places=1);self.assertAlmostEqual(ctx['availability_pct_during'],90.4,places=1)
    def test_instamart_hyderabad_two_sunscreen_po_gaps(self):
        sunscreen_skus=set(self.data['products'].loc[self.data['products'].category.eq('Sunscreen'),'sku_code'])
        x=ordering_gaps(self.data);x=x[(x.platform=='Instamart')&(x.city=='Hyderabad')&x.sku_code.isin(sunscreen_skus)]
        self.assertEqual(len(x),2);self.assertTrue((x.consecutive_missing_weeks==2).all());self.assertTrue(x.resumed_after_gap.all())
        self.assertTrue((x.export_coverage_pct>=99).all())

if __name__=='__main__':unittest.main(verbosity=2)
