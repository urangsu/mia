"""Synthetic grouped report tests. No live price feeds or company accounts."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from market_catalog import friendly_product, identify_series, describe_fmb
from market_report_ui import dashboard_payload


class GroupedMarketReportTests(unittest.TestCase):
    def fixture(self):
        catalog = [
            ('시리즈 키(수정 금지)', '짧은 표시명', '단위·원본 기준'),
            ('FMB|MB-LI-0029|USD/t|Actual|MID', 'LC', 'Lithium carbonate battery grade cif China Japan Korea'),
            ('FMB|MB-BMS-0012|USD/t|Actual|MID', 'BM', 'Black mass high cobalt NCM South Korea'),
            ('NAVER|SP500|point|Actual|MID', 'SP500', 'NAVER / point'),
        ]
        daily = [
            ('고시일','LC','BM','SP500'),
            ('','FMB','FMB','NAVER'),
            ('2026-09-01',100.5,190.75,5000),
            ('2026-09-02',None,191.25,5015),
            ('2026-10-01',102,192.0,None),
        ]
        cap = [('순위','종목명','코드','시장일','시가총액','단위','상태','출처'),
               (1,'삼성전자','005930','2026-10-01',12345,'억원','final','NAVER')]
        return SimpleNamespace(
            _sheets={'일별시세':daily,'가격열설정':catalog},
            tables={'보고용_시총':cap},
            as_of='2026-10-02T09:00:00+09:00',
            snapshot_id='abc123',
        )

    def test_readable_name_is_not_a_bare_code(self):
        self.assertIn('탄산리튬', friendly_product('MB-LI-0029'))
        self.assertIn('Black Mass', friendly_product('MB-BMS-0012'))
        self.assertNotEqual(friendly_product('MB-LI-0029'),'MB-LI-0029')
        self.assertIn('확인 필요', friendly_product('MB-UNKNOWN'))
        self.assertEqual(describe_fmb('MB-MN-0001')[0],'manganese')

    def test_known_and_us_groups_are_typed(self):
        self.assertEqual(identify_series('NAVER|SP500|point|Actual|MID')[0],'us_market')
        self.assertEqual(identify_series('NAVER|KOSPI|point|Actual|MID')[0],'kr_market')
        self.assertEqual(identify_series('FX_USD_KRW_per_1')[0],'fx')
        self.assertEqual(identify_series('FMB|MB-BMS-0012|USD/t|Actual|MID')[0],'bm_ncm')

    def test_validated_daily_values_only_and_no_missing_as_zero(self):
        c=self.fixture()
        out=dashboard_payload(c)
        groups={g['id']:g for g in out['groups']}
        self.assertEqual(len(groups['lithium_carbonate']['series'][0]['points']),2)
        self.assertEqual(groups['lithium_carbonate']['series'][0]['points'][0],
                         {'date':'2026-09-01','value':100.5})
        self.assertNotIn({'date':'2026-09-02','value':0},groups['lithium_carbonate']['series'][0]['points'])
        self.assertEqual(groups['us_market']['series'][0]['name'],'S&P 500')
        self.assertEqual(groups['us_market']['series'][0]['points'][-1]['date'],'2026-09-02')
        self.assertEqual(groups['nickel']['series'],[])
        self.assertEqual(groups['nickel']['status'],'수집 데이터 없음')
        self.assertEqual(out['rankings_us'],[])
        self.assertEqual(out['rankings_kr'][0]['code'],'005930')

    def test_no_cross_unit_scaling_and_no_price_fabrication(self):
        c=self.fixture()
        out=dashboard_payload(c)
        all_series=[s for g in out['groups'] for s in g['series']]
        self.assertEqual(len(all_series),3)
        for series in all_series:
            self.assertEqual(series['source'],identify_series(series['key'])[2])
            self.assertTrue(all(isinstance(p['value'],float) for p in series['points']))
        self.assertFalse(any(x['source']=='LME' for x in all_series))

    def test_local_js_is_external_and_has_no_browser_fetch(self):
        script=Path(__file__).with_name('market_report.js').read_text(encoding='utf-8')
        self.assertNotIn('fetch(',script)
        self.assertNotIn('XMLHttpRequest',script)
        self.assertIn('trend-tooltip',script)

if __name__=='__main__':
    unittest.main()
