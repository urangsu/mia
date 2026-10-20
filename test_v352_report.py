# -*- coding: utf-8 -*-
"""v3.5.2: two report header rows, FMB MID only, preserved third-party columns."""
import unittest
from types import SimpleNamespace
from excel_secure import make_sheets, merge_external_columns, order_managed_columns, excel_value
from smbs_rates import FXQuote


def p(symbol, date, price_mode='Actual', mid='10', low='9', high='11'):
    return SimpleNamespace(symbol=symbol,date=date,unit='USD/t',price_mode=price_mode,
                           period_label='',view_key='view',mid=mid,low=low,high=high,
                           change_pct=None,description='description',widget='grid',source='FMB')

class V352ReportTests(unittest.TestCase):
    def test_mid_only_and_forecast_then_actual(self):
        rows=[p('MB-CO-0005','2026-10-16',mid='100', high='110'),
              p('MB-LI-0029','2026-10-16',price_mode='Forecast',mid='12'),
              p('MB-LI-0029','2026-10-16',price_mode='Actual',mid='10')]
        sheets=make_sheets(rows,[],[])
        header=sheets['일별시세'][0]
        self.assertEqual(header,('고시일','LC(전망)','LC','Co'))
        self.assertEqual(sheets['일별시세'][1],('','FMB','FMB','FMB'))
        self.assertEqual(sheets['일별시세'][2],('2026-10-16',12.0,10.0,100.0))
        self.assertTrue(all(not r[0].endswith('|LOW') and not r[0].endswith('|HIGH')
                            for r in sheets['가격열설정'][1:]))
        self.assertEqual(len(sheets['RawData']),4)
    def test_report_omits_low_high_only_dates(self):
        rows=[p('MB-LI-0029','2026-10-15',mid=None),
              p('MB-LI-0029','2026-10-16',mid='15')]
        sheets=make_sheets(rows,[],[])
        self.assertEqual(len(sheets['일별시세']),3)
        self.assertEqual(sheets['일별시세'][2][0],'2026-10-16')
        self.assertEqual(sheets['월별건수'][2][1],1)
    def test_fx_per_column_source_no_source_column(self):
        sheets=make_sheets([p('MB-LI-0029','2026-10-16')],[],[
            FXQuote('2026-10-16','USD','1348.50','-9.90',1)])
        daily=sheets['일별시세']
        self.assertEqual(daily[0][:2],('고시일','LC'))
        self.assertEqual(daily[1],('','FMB','SMBS'))
        self.assertEqual(daily[2][2],1348.5)
        self.assertEqual(sheets['환율원본'][1][3],-9.9)
    def test_existing_user_series_aligns_by_date_during_regeneration(self):
        new=[('고시일','LC','Co'),('','FMB','FMB'),
             ('2026-10-15',15,50),('2026-10-16',16,51),('2026-10-19',19,52)]
        old=[('고시일','출처','LC(하한)','LC','회사기록'),
             ('','', 'FMB','FMB','수기'),
             ('2026-10-16','FMB',14,16,300),
             ('2026-10-15','FMB',12,15,200)]
        merged=merge_external_columns(new,old,{'LC(하한)','LC'})
        self.assertEqual(merged[0],('고시일','LC','Co','회사기록'))
        self.assertEqual(merged[1],('','FMB','FMB','수기'))
        self.assertEqual([row[-1] for row in merged[2:]], [200,300,None])
    def test_stable_order_appends_new_codes(self):
        x=make_sheets([p('MB-LI-0029','2026-10-16'),p('MB-CO-0005','2026-10-16')],[],[])
        spec=x['가격열설정']; old=[spec[2][0],spec[1][0]]
        order_managed_columns(x,old,{old[0]:'CO_고정'})
        self.assertEqual(x['일별시세'][0][:3],('고시일','CO_고정','LC'))
        self.assertEqual(x['일별시세'][2][:3],('2026-10-16',10.0,10.0))
    def test_migrated_old_low_high_catalog_resets_order(self):
        x=make_sheets([p('MB-LI-0029','2026-10-16'),p('MB-CO-0005','2026-10-16')],[],[])
        old=['FMB|MB-CO-0005|USD/t|Actual|MID',
             'FMB|MB-LI-0029|USD/t|Actual|LOW',
             'FMB|MB-LI-0029|USD/t|Actual|MID']
        order_managed_columns(x,old,{})
        self.assertEqual(x['일별시세'][0][:3],('고시일','LC','Co'))
    def test_manual_text_stays_as_text_and_numeric_columns_numeric(self):
        self.assertEqual(excel_value('일별시세','LC','15.3'),15.3)
        self.assertEqual(excel_value('일별시세','고시일','2027-01-01'),'2027-01-01')

if __name__=='__main__':unittest.main()
