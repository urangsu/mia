import unittest
from pathlib import Path
from types import SimpleNamespace
from smbs_rates import prepare_excel_series
from excel_secure import make_sheets,excel_value
import FastmarketsCollector_v3_4 as m
class V351DailyTests(unittest.TestCase):
    def test_two_header_rows_and_short_titles(self):
        p=SimpleNamespace(symbol='MB-LI-0029',unit='$/kg',price_mode='Actual',period_label='',view_key='a',date='2026-10-16',mid='14',low='13',high='15',change_pct=None,description='LC CJK',widget='탄산리튬',source='AG Grid')
        out=make_sheets([p],[],[])
        self.assertEqual(out['일별시세'][0],('고시일','LC'))
        self.assertEqual(out['일별시세'][1],('','FMB'))
        self.assertEqual(out['일별시세'][2],('2026-10-16',14000.0))
        self.assertNotIn('LC(하한)',out['일별시세'][0])
        self.assertNotIn('LC(상한)',out['일별시세'][0])
    def test_daily_scroll_budget(self):
        offsets,history=m.daily_vertical_positions(500000,250,7)
        self.assertLessEqual(len(offsets),18);self.assertFalse(history)
        offsets,history=m.daily_vertical_positions(500000,250,0)
        self.assertTrue(history);self.assertEqual(offsets[-1],500000)
    def test_conflicting_mid_quarantined_even_when_one_view_is_bounded(self):
        one=SimpleNamespace(symbol='MB-CO-0005',unit='$/lb',price_mode='Actual',period_label='',view_key='a',date='2026-10-16',mid='22.93',low='21',high='24')
        two=SimpleNamespace(symbol='MB-CO-0005',unit='$/lb',price_mode='Actual',period_label='',view_key='b',date='2026-10-16',mid='50552',low=None,high=None)
        issues=[];d=prepare_excel_series([one,two],[],issues=issues)
        # The second panel is a verified Tonne conversion, not a conflicting dollar-per-pound price.
        self.assertEqual(d['2026-10-16']['FMB|MB-CO-0005|$/lb|Actual|MID'],50552.0)
        self.assertFalse(issues)
    def test_conflicts_without_evidence_blank(self):
        def a(v,id):return SimpleNamespace(symbol='MB-CO-0005',unit='$/lb',price_mode='Actual',period_label='',view_key=id,date='2026-10-16',mid=v,low=None,high=None)
        i=[];d=prepare_excel_series([a('22','a'),a('55','b')],[],issues=i)
        self.assertNotIn('FMB|MB-CO-0005|$/lb|Actual|MID',d.get('2026-10-16',{}))
        self.assertEqual(len(i),1)
if __name__=='__main__':unittest.main()
