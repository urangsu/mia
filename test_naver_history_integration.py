import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch
import naver_markets as n
from report_model import build_context


HTML='''<table><tr><th>날짜</th><th>종가</th></tr>
<tr><td>2026. 10. 26.</td><td>120,000</td></tr>
<tr><td>2026. 10. 23.</td><td>100,000</td></tr></table>'''


class Driver:
    def __init__(self):
        self.current_window_handle='original'; self.window_handles=['original']
        self.current_url='about:blank'; self.switch_to=self
    def new_window(self,kind):
        self.current_window_handle='owned'; self.window_handles.append('owned')
    def window(self,handle): self.current_window_handle=handle
    def get(self,url): self.current_url=url
    @property
    def page_source(self): return HTML
    def close(self): self.window_handles.remove(self.current_window_handle)


class HistoryIntegrationTests(unittest.TestCase):
    def test_ranking_names_flow_to_actual_stock_history(self):
        from test_naver_current_cap import CurrentCapDOMTests
        class RankedDriver(Driver):
            @property
            def page_source(self):
                return CurrentCapDOMTests().page() if 'capitalization' in self.current_url else HTML
        pages=(('equities','https://stock.naver.com/market/stock/kr/stocklist/capitalization'),
               ('history:005930','https://stock.naver.com/domestic/stock/005930/price'))
        with patch.object(n,'PAGES',pages),patch.object(n.time,'monotonic',side_effect=range(1000)),patch.object(n.time,'sleep'):
            result=n.collect(RankedDriver(),lambda:False,lambda s:None)
        closes=[r for r in result['equities'] if r['market_date']]
        self.assertEqual(len(closes),2)
        self.assertTrue(all(r['name']=='테스트전자' for r in closes))

    def test_all_pages_unavailable_is_failed_not_partial_success(self):
        class OfflineDriver(Driver):
            def get(self,url): raise TimeoutError('offline fixture')
        with patch.object(n,'PAGES',(('history:KOSPI','https://stock.naver.com/domestic/index/KOSPI/price'),)):
            result=n.collect(OfflineDriver(),lambda:False,lambda s:None)
        self.assertEqual(result['status'],'failed')

    def test_one_unavailable_public_page_does_not_discard_other_history(self):
        class FlakyDriver(Driver):
            def get(self,url):
                if '/KOSPI/' in url: raise TimeoutError('synthetic source timeout')
                super().get(url)
        driver=FlakyDriver()
        pages=(('history:KOSPI','https://stock.naver.com/domestic/index/KOSPI/price'),
               ('history:005490','https://stock.naver.com/domestic/stock/005490/price'))
        with patch.object(n,'PAGES',pages): result=n.collect(driver,lambda:False,lambda s:None)
        self.assertEqual(result['status'],'partial')
        self.assertEqual(len(result['equities']),2)
        self.assertTrue(any('KOSPI' in w and 'timeout' in w for w in result['warnings']))
        self.assertEqual(driver.window_handles,['original'])

    def test_live_cap_report_shows_snapshot_comparison_without_faking_market_day(self):
        from test_cap_snapshot_compare import capture
        import FastmarketsCollector_v3_4 as core
        with tempfile.TemporaryDirectory() as temp:
            db=core.path_bundle(Path(temp))['db']
            with closing(sqlite3.connect(db)) as cx, cx:
                n.initialize_schema(cx)
                # Actual first-run stock history has no capitalization; it must
                # not block the separate live-cap snapshot comparison.
                cx.execute('INSERT INTO equity_rank_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                           ('005490',None,'POSCO홀딩스','2026-10-26','2026-10-27T08:30:00+09:00','100',None,None,None,'원','KRW','stale','fixture://history',json.dumps({'close_verified':True})))
                for stamp,value in [('2026-10-26T08:30:00+09:00','100'),('2026-10-27T08:30:00+09:00','110')]:
                    row=capture('005930',stamp,value)
                    cx.execute('INSERT INTO naver_raw_captures(captured_at,entity,entity_key,raw_json,reason) VALUES(?,?,?,?,?)',
                               (stamp,'equities','005930',row['raw_json'],'undated live'))
            context=build_context(temp,captured_at='2026-10-27T08:30:00+09:00')
            table=context.tables['보고용_시총']
            self.assertEqual(len(table),2)
            self.assertIsNone(table[1][3])
            self.assertEqual(table[1][6],'capture_pair')
            self.assertEqual(table[1][10:13],(100.0,10.0,10.0))
            self.assertTrue(any('수집시점' in w for w in context.warnings))

    def test_first_run_history_reaches_db_stock_table_and_preserves_tab(self):
        with tempfile.TemporaryDirectory() as temp:
            import FastmarketsCollector_v3_4 as core
            db=core.path_bundle(Path(temp))['db']; driver=Driver()
            with patch.object(n,'PAGES',(('history:005490','https://stock.naver.com/domestic/stock/005490/price'),)):
                result=n.collect_and_save(driver,db,lambda:False,lambda s:None)
            self.assertEqual(result['equities'],2)
            self.assertEqual(driver.window_handles,['original'])
            self.assertEqual(driver.current_window_handle,'original')
            context=build_context(temp,captured_at='2026-10-27T08:30:00+09:00')
            stocks=context.tables['보고용_주가']
            self.assertEqual(len(stocks),2)
            self.assertEqual(stocks[1][0],'005490')
            self.assertEqual(stocks[1][2:8],('2026-10-26',120000.0,'2026-10-23',100000.0,20000.0,20.0))
            self.assertEqual(stocks[1][9],'close_pair_naver')

    def test_old_daily_table_pair_is_visible_but_not_claimed_current(self):
        import FastmarketsCollector_v3_4 as core
        with tempfile.TemporaryDirectory() as temp:
            db=core.path_bundle(Path(temp))['db']
            from naver_dom_history import parse_daily_history
            old=HTML.replace('10. 26.','10. 21.').replace('10. 23.','10. 20.')
            rows=parse_daily_history(old,'KOSPI','https://stock.naver.com/domestic/index/KOSPI/price',
                                     '2026-10-27T08:30:00+09:00')['rows']
            with patch.object(n,'collect',return_value=dict(indicators=rows,equities=[],status='partial',warnings=[])):
                n.collect_and_save(None,db,lambda:False)
            context=build_context(temp,captured_at='2026-10-27T08:30:00+09:00')
            row=context.tables['보고용_시장지표'][1]
            self.assertEqual(row[2],120000.0)
            self.assertEqual(row[8],'stale_history')


if __name__=='__main__': unittest.main()
