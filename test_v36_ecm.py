# -*- coding: utf-8 -*-
import unittest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock,patch
from ecm_excel_sync import build_plan, date_key, ECMBlocked, plan_fingerprint
from series_mapping import compact_series_label
from ecm_automation import _is_target_link

K_LI='FMB|MB-LI-0029|$/kg|Unspecified|MID'
K_CO='FMB|MB-CO-0005|$/lb|Unspecified|MID'
K_FX='FX_USD_KRW_per_1'
SRC_CATALOG=[('시리즈 키(수정 금지)','짧은 표시명','단위'),(K_LI,'LC','Li carbonate'),(K_CO,'Co','Co RTM'),(K_FX,'USD','KRW')]
DST_CATALOG=SRC_CATALOG[:]
SOURCE=[('고시일','LC','Co','USD'),('','FMB','FMB','SMBS'),('2026-10-16',17.1,24.1,1352.0),('2026-10-19',18.2,25.3,1342.4)]

class ECMTest(unittest.TestCase):
    def test_append_row_and_preserve_user_inserted_col(self):
        dst=[('고시일','LC','SMM(수기)','Co','USD'),('','FMB','SMM','FMB','SMBS'),('2026-10-16',17.1,100,24.1,1352.0)]
        p=build_plan(SOURCE,SRC_CATALOG,dst,DST_CATALOG)
        self.assertEqual(p['stats']['new_dates'],1)
        self.assertEqual(p['new_dates'][0]['row'],4)
        self.assertEqual(p['stats']['fill'],3)
        self.assertEqual({e['col'] for e in p['edits']},{2,4,5})
        self.assertEqual(p['stats']['correction'],0)
    def test_same_values_no_changes(self):
        p=build_plan(SOURCE,SRC_CATALOG,SOURCE,DST_CATALOG)
        self.assertEqual(p['stats']['fill'],0)
        self.assertEqual(p['stats']['unchanged'],6)
        self.assertFalse(p['new_dates'])
    def test_reordered_series(self):
        dst=[('고시일','USD','Co','LC'),('','SMBS','FMB','FMB'),('2026-10-16',1352.0,24.1,17.1)]
        p=build_plan(SOURCE,SRC_CATALOG,dst,DST_CATALOG)
        self.assertEqual({e['key']:e['col'] for e in p['edits']}, {K_LI:4,K_CO:3,K_FX:2})
    def test_ambiguous_headers_abort(self):
        dst=[('고시일','LC','LC','Co','USD'),('','FMB','FMB','FMB','SMBS'),('2026-10-16',17.1,17.1,24.1,1352.0)]
        with self.assertRaisesRegex(ECMBlocked,'헤더가 두 번'):
            build_plan(SOURCE,SRC_CATALOG,dst,DST_CATALOG)
    def test_no_guess_if_renamed_header(self):
        dst=[('고시일','리튬','Co','USD'),('','FMB','FMB','SMBS'),('2026-10-16',17.1,24.1,1352.0)]
        with self.assertRaisesRegex(ECMBlocked,'헤더가 가격열설정과 다릅니다'):
            build_plan(SOURCE,SRC_CATALOG,dst,DST_CATALOG)
    def test_forecast_distinct_and_new_column(self):
        k='FMB|MB-LI-0029|$/kg|Forecast|MID'
        src=[('고시일','LC','LC(전망)'),('','FMB','FMB'),('2026-10-19',18.2,19.3)]
        cat=[SRC_CATALOG[0],SRC_CATALOG[1],(k,'LC(전망)','forecast')]
        dst=[('고시일','LC'),('','FMB'),('2026-10-19',18.2)]
        p=build_plan(src,cat,dst,SRC_CATALOG[:2])
        self.assertEqual(p['stats']['new_columns'],1)
        self.assertEqual(p['new_columns'][0]['col'],3)
    def test_corrections_require_approval_plan(self):
        dst=[('고시일','LC','Co','USD'),('','FMB','FMB','SMBS'),('2026-10-16',1,24.1,1352.0)]
        p=build_plan(SOURCE,SRC_CATALOG,dst,DST_CATALOG)
        self.assertEqual(p['stats']['correction'],1)
        self.assertEqual(p['edits'][0]['previous'],1.0)
    def test_bad_dates_stop_instead_of_guess(self):
        for v in ('10월19일','Oct','',None):
            with self.assertRaises(ECMBlocked):date_key(v)
        self.assertEqual(date_key(46314),'2026-10-19')
        self.assertEqual(date_key(44852,date1904=True),'2026-10-19')
    def test_duplicate_dates_stop(self):
        dest=SOURCE+[('2026-10-19',18.2,25.3,1342.4)]
        with self.assertRaisesRegex(ECMBlocked,'중복'):
            build_plan(SOURCE,SRC_CATALOG,dest,DST_CATALOG)
    def test_key_caption_includes_geo(self):
        self.assertEqual(compact_series_label('FMB|MB-BMS-0004|% payable|Unspecified|MID'),'BM(NCM Ni) EU')
        self.assertEqual(compact_series_label('FMB|MB-BMS-0012|$/tonne|Unspecified|MID'),'BM(NCM 고Co) KR')
        self.assertEqual(compact_series_label('FMB|MB-BMS-0010|% payable|Forecast|MID'),'BM(LCO Co) KR(전망)')
    def test_filename_is_used_for_link_validation(self):
        node=MagicMock();node.ControlTypeName='HyperlinkControl';node.Name='fastmarkets_prices.xlsx';node.IsOffscreen=False
        node.BoundingRectangle.left=1;node.BoundingRectangle.top=1;node.BoundingRectangle.right=120;node.BoundingRectangle.bottom=20
        self.assertTrue(_is_target_link(node,'fastmarkets_prices.xlsx'))
        self.assertFalse(_is_target_link(node,'다른파일.xlsx'))
    def test_plan_hash_changes_after_reordering(self):
        a=build_plan(SOURCE,SRC_CATALOG,SOURCE,DST_CATALOG)
        b=build_plan(SOURCE,SRC_CATALOG,[('고시일','USD','Co','LC'),('','SMBS','FMB','FMB'),('2026-10-16',1352.0,24.1,17.1)],DST_CATALOG)
        self.assertNotEqual(plan_fingerprint(a),plan_fingerprint(b))

if __name__=='__main__':unittest.main()

class ECMMonthlyTest(unittest.TestCase):
    def test_monthly_reordered_and_extra_col(self):
        src=[('기준월','LC','USD'),('','FMB','SMBS'),('2026-09',16.1,1300.0),('2026-10',17.2,1342.0)]
        cat=[SRC_CATALOG[0],SRC_CATALOG[1],SRC_CATALOG[3]]
        dst=[('기준월','수기','USD','LC'),('','외부','SMBS','FMB'),('2026-09',5,1300.0,16.1)]
        p=build_plan(src,cat,dst,cat,period_type='monthly')
        self.assertEqual(p['stats']['new_dates'],1)
        self.assertEqual({e['col'] for e in p['edits']},{3,4})
    def test_invalid_month_aborts(self):
        src=[('기준월','LC'),('','FMB'),('2026-13',2.5)]
        cat=SRC_CATALOG[:2]
        with self.assertRaises(ECMBlocked):
            build_plan(src,cat,[('기준월','LC'),('','FMB')],cat,period_type='monthly')

class ECMLockTest(unittest.TestCase):
    def test_ecm_open_not_inside_same_exclusive_lock(self):
        import inspect, gui_v36
        src=inspect.getsource(gui_v36.main_gui)
        start=src.index('    def preview_ecm(')
        end=src.index('    def apply_ecm(',start)
        self.assertNotIn('with exclusive_ecm_job()',src[start:end])
