"""Synthetic DOM contract tests; these are NOT live NAVER acceptance."""
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).parent


class NaverTests(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location('naver_markets', HERE / 'naver_markets.py')
        self.assertIsNotNone(spec)
        self.assertTrue(Path(spec.origin).exists(), 'NAVER module is not implemented')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_split_numeric_and_a11y_sign(self):
        m = self.module()
        html = '''<article data-mini-chart-id="KOSPI" data-unit="포인트"><b>코스피</b>
        <span data-field="value"><i>2,</i><i>500</i><i>.00</i></span>
        <span data-field="change">하락 25.00</span><span data-field="pct">하락 0.99%</span>
        <time>2026.10.16</time><span>장마감</span><span>가격이 업데이트되었습니다 999</span></article>'''
        result = m.parse_indicators(html, '2026-10-19T10:00:00+09:00')
        row = result['rows'][0]
        self.assertEqual((row['value'], row['change'], row['pct']), ('2500.00', '-25.00', '-0.99'))
        self.assertEqual(row['market_date'], '2026-10-16')
        self.assertEqual(row['status'], 'stale')

    def test_unknown_date_and_units_not_invented(self):
        m = self.module()
        result = m.parse_indicators('<div data-mini-chart-id="GOLD"><span data-field="value">2700</span></div>')
        row = result['rows'][0]
        self.assertIsNone(row['market_date'])
        self.assertIsNone(row['unit'])
        self.assertEqual(row['status'], 'unverified')
        self.assertTrue(result['warnings'])

    def test_arithmetic_independently_rejects_mismatch(self):
        m = self.module()
        html = '<div data-mini-chart-id="NASDAQ" data-date="2026-10-19"><span data-field="value">110</span><span data-field="change">+10</span><span data-field="pct">+90%</span>장마감</div>'
        self.assertEqual(m.parse_indicators(html)['rows'][0]['status'], 'unverified')

    def test_capitalization_codes_deduplicated_and_extra_target(self):
        m = self.module()
        html = '<table data-market-scope="KRX_ALL">'+''.join('<tr data-nlogs="stock" data-date="2026-10-19" data-rank="%s"><td><a href="/domestic/stock/%s/total">회사</a></td><td data-field="price">1,000</td></tr>' % (rank, code) for rank, code in [(1,'005930'),(2,'005490'),(12,'005490'),(11,'000660')])+'</table>'
        rows = m.parse_capitalization(html)['rows']
        self.assertEqual([r['stock_code'] for r in rows], ['005930','005490'])

    def test_persistence_revisions_and_failed_retry(self):
        m = self.module()
        with tempfile.TemporaryDirectory() as temp:
            db = str(Path(temp) / 'test.db')
            payload = {'indicators': m.parse_indicators('<div data-mini-chart-id="KOSPI" data-unit="포인트" data-date="2026-10-19"><span data-field="value">110.00</span><span data-field="change">+10.00</span><span data-field="pct">+10.00%</span>장마감</div>', '2026-10-19T18:00:00+09:00')['rows'], 'equities': [], 'warnings': [], 'status':'partial'}
            with patch.object(m, 'collect', return_value=payload):
                self.assertEqual(m.collect_and_save(None, db, lambda:False)['indicators'],1)
                m.collect_and_save(None, db, lambda:False)
                payload['indicators'][0]['value'] = '111.00'
                m.collect_and_save(None, db, lambda:False)
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('SELECT COUNT(*) FROM market_indicators').fetchone()[0],1)
                self.assertEqual(cx.execute('SELECT COUNT(*) FROM naver_revisions').fetchone()[0],1)
                self.assertEqual(cx.execute('SELECT COUNT(*) FROM naver_daily_runs').fetchone()[0],0)

    def test_cancel_and_redirect_cleanup(self):
        m = self.module()
        class Switch:
            def __init__(self, driver): self.d = driver
            def new_window(self, kind): self.d.current_window_handle='ours'; self.d.window_handles.append('ours')
            def window(self, handle): self.d.current_window_handle=handle
        class Driver:
            current_window_handle='original'
            current_url='about:blank'
            page_source=''
            def __init__(self): self.window_handles=['original']; self.switch_to=Switch(self)
            def get(self,url): self.current_url='https://evil.example/redirect'
            def close(self): self.window_handles.remove(self.current_window_handle)
        d = Driver()
        result=m.collect(d, lambda:False, lambda msg:None)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(d.window_handles,['original'])
        self.assertEqual(d.current_window_handle,'original')

    def test_accessibility_announcement_does_not_erase_siblings(self):
        m=self.module()
        html='<div data-mini-chart-id="KOSPI" data-unit="포인트" data-date="2026-10-19"><span>가격이 업데이트되었습니다</span><span data-field="value">1, <i>100</i><i>.00</i></span><span data-field="change">상승 100</span><span data-field="pct">상승 10%</span>장마감</div>'
        row=m.parse_indicators(html)['rows'][0]
        self.assertEqual(row['value'],'1100.00')
        self.assertNotEqual(row['status'],'unverified')

    def test_legacy_finance_table_uses_headers_not_css_hashes(self):
        m=self.module()
        html='''<p class="date" data-market-asof="2026-10-19">2026.10.19 기준</p><table data-market-scope="KRX_ALL"><thead><tr><th>N</th><th>종목명</th><th>현재가</th><th>전일비</th><th>등락률</th><th>시가총액</th></tr></thead><tbody><tr data-unit="원"><td>1</td><td><a href="/item/main.naver?code=005930">삼성전자</a></td><td>110,000</td><td><span>상승</span>10,000</td><td>+10.00%</td><td>1,000</td></tr></tbody></table>'''
        row=m.parse_capitalization(html)['rows'][0]
        self.assertEqual(row['price'],'110000')
        self.assertEqual(row['market_cap'],'1000')
        self.assertNotEqual(row['status'],'unverified')

    def test_failed_collect_cannot_overwrite_previous_good(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as temp:
            db=str(Path(temp)/'test.db')
            row=m.parse_indicators('<div data-mini-chart-id="KOSPI" data-unit="포인트" data-date="2026-10-19"><span data-field="value">110</span><span data-field="change">10</span><span data-field="pct">10</span></div>')['rows'][0]
            payload={'indicators':[row],'equities':[],'warnings':[],'status':'partial'}
            with patch.object(m,'collect',return_value=payload):
                m.collect_and_save(None,db,lambda:False)
                row['value']='999'; payload['status']='failed'
                m.collect_and_save(None,db,lambda:False)
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('SELECT value FROM market_indicators').fetchone()[0],'110')

    def test_complete_fixture_and_daily_force_gate(self):
        m=self.module()
        captured='2026-10-19T18:00:00+09:00'
        indicator=m.parse_indicators((HERE/'fixtures/naver_indicators_synthetic.html').read_text(),captured)
        equities=m.parse_capitalization((HERE/'fixtures/naver_capitalization_synthetic.html').read_text(),captured)
        self.assertEqual(len(indicator['rows']),8)
        self.assertTrue(all(r['status']=='final' for r in indicator['rows']))
        self.assertEqual(len(equities['rows']),11)
        self.assertTrue(all(m.is_verified_close(r) for r in equities['rows']))
        with tempfile.TemporaryDirectory() as temp:
            db=str(Path(temp)/'test.db')
            payload={'indicators':indicator['rows'],'equities':equities['rows'],'warnings':[],'status':'complete'}
            with patch.object(m,'collect',return_value=payload) as collect:
                m.collect_and_save(None,db,lambda:False)
                self.assertEqual(m.collect_and_save(None,db,lambda:False)['status'],'skipped_daily')
                self.assertEqual(collect.call_count,1)
                m.collect_and_save(None,db,lambda:False,force=True)
                self.assertEqual(collect.call_count,2)

    def test_wrong_market_scope_does_not_create_krx_ranks(self):
        m=self.module()
        html='<table data-market-scope="KOSPI"><tr data-rank="1" data-date="2026-10-19"><a href="/domestic/stock/005930/total">삼성</a><span data-field="price">100</span></tr><tr data-rank="3"><a href="/domestic/stock/005490/total">POSCO</a></tr></table>'
        result=m.parse_capitalization(html)
        self.assertEqual([r['stock_code'] for r in result['rows']],['005490'])
        self.assertIsNone(result['rows'][0]['rank'])
        self.assertTrue(result['warnings'])

    def test_nlogs_identifiers_and_per_card_dates(self):
        m=self.module()
        html='<div data-date="2026-10-19">'+''.join('<article data-nlogs="%s" data-date="2026-10-16"><span class="Price_value">1,<i>100</i>.00</span><span class="Price_change">상승 100</span><span class="Price_rate">상승 10%%</span>장마감</article>' % alias for alias in ('nix.spi500','nix.ixic','nix.us10yt','nix.kr10yt','nix.wgold','nix.wti'))+'</div>'
        rows=m.parse_indicators(html,'2026-10-19T10:00:00+09:00')['rows']
        self.assertEqual(len(rows),6)
        self.assertTrue(all(r['market_date']=='2026-10-16' for r in rows))

    def test_unknown_unit_is_not_final_even_with_date_and_arithmetic(self):
        m=self.module()
        html='<article data-mini-chart-id="KOSPI" data-date="2026-10-19"><span data-field="value">110</span><span data-field="change">10</span><span data-field="pct">10</span>장마감</article>'
        self.assertEqual(m.parse_indicators(html)['rows'][0]['status'],'unverified')
        equity='<tr data-stock-code="005490" data-date="2026-10-19"><span data-field="price">110</span>장마감</tr>'
        self.assertEqual(m.parse_capitalization(equity)['rows'][0]['status'],'unverified')

    def test_posco_detail_fallback_has_no_invented_rank(self):
        m=self.module()
        html='''<head><meta property="og:url" content="https://finance.naver.com/item/main.naver?code=005490"></head><div class="wrap_company"><h2>POSCO홀딩스</h2><span class="date">2026.10.19 기준</span></div><div class="rate_info"><p class="no_today">110,000</p><p class="no_exday">상승 10,000 (+10.00%)</p><span>원 장마감</span></div>'''
        rows=m.parse_capitalization(html)['rows']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['stock_code'],'005490')
        self.assertIsNone(rows[0]['rank'])
        self.assertEqual(rows[0]['price'],'110000')

    def test_aria_direction_and_conflict_fail_closed(self):
        m=self.module()
        for attrs,text in [('aria-label="하락"','10'),('', '<i aria-label="하락"></i>10'),('aria-label="하락"','+10')]:
            html='<article data-mini-chart-id="KOSPI" data-unit="포인트" data-date="2026-10-19"><span data-field="value">110</span><span data-field="change" %s>%s</span><span data-field="pct" aria-label="하락">10</span>장마감</article>'%(attrs,text)
            row=m.parse_indicators(html)['rows'][0]
            self.assertEqual(row['status'],'unverified')
            self.assertNotEqual(row['change'],'10')

    def test_equities_do_not_borrow_sibling_dates_and_require_deltas(self):
        m=self.module()
        html='<table data-market-scope="KRX_ALL"><tr data-stock-code="005930" data-rank="1" data-unit="원" data-date="2026-10-19"><span data-field="price">100</span></tr><tr data-stock-code="005490" data-unit="원"><span data-field="price">200</span></tr></table>'
        rows=m.parse_capitalization(html)['rows']
        self.assertIsNone(rows[1]['market_date'])
        self.assertTrue(all(r['status']=='unverified' for r in rows))
        html=html.replace('data-market-scope="KRX_ALL"','data-market-scope="KRX_ALL" data-date="2026-10-16"')
        self.assertEqual(m.parse_capitalization(html)['rows'][1]['market_date'],'2026-10-16')

    def test_commodity_unit_needs_denomination_and_currency(self):
        m=self.module()
        template='<article data-mini-chart-id="%s" data-unit="%s" data-date="2026-10-19"><span data-field="value">110</span><span data-field="change">10</span><span data-field="pct">10</span>장마감</article>'
        for key,unit in [('GOLD','USD'),('WTI','USD')]:
            self.assertEqual(m.parse_indicators(template%(key,unit))['rows'][0]['status'],'unverified')
        for key,unit in [('GOLD','USD/oz'),('WTI','USD/bbl')]:
            row=m.parse_indicators(template%(key,unit))['rows'][0]
            self.assertEqual(row['currency'],'USD')
            self.assertNotEqual(row['status'],'unverified')

    def test_readiness_does_not_stop_at_first_hydrated_row(self):
        m=self.module()
        complete=(HERE/'fixtures/naver_indicators_synthetic.html').read_text()
        class Switch:
            def __init__(self,d): self.d=d
            def new_window(self,k): self.d.current_window_handle='ours'; self.d.window_handles.append('ours')
            def window(self,k): self.d.current_window_handle=k
        class Driver:
            current_window_handle='original'
            current_url='about:blank'
            def __init__(self): self.window_handles=['original'];self.switch_to=Switch(self);self.reads=0
            def get(self,url):self.current_url=url
            @property
            def page_source(self):
                self.reads+=1
                return complete.split('</article>')[0]+'</article>' if self.reads==1 else complete
            def close(self):self.window_handles.remove(self.current_window_handle)
        d=Driver()
        with patch.object(m,'PAGES',(('indicators','https://stock.naver.com/market'),)), patch.object(m.time,'sleep'):
            result=m.collect(d,lambda:False,lambda msg:None)
        self.assertEqual(len(result['indicators']),8)
        self.assertGreaterEqual(d.reads,2)

    def test_cap_unit_is_explicit_and_price_unit_is_never_reused(self):
        m=self.module()
        template='<tr data-stock-code="005490" data-unit="원" data-date="2026-10-19" %s><span data-field="price">1100</span><span data-field="change">100</span><span data-field="pct">10</span><span data-field="market_cap">10000</span>%s</tr>'
        for attr,child,expected in [('', '',None),('data-market-cap-unit="억원"','', '억원'),('', '<span data-field="market_cap_unit">백만원</span>','백만원')]:
            row=m.parse_capitalization(template%(attr,child))['rows'][0]
            self.assertEqual(row['unit'],'원')
            self.assertEqual(json.loads(row['raw_json']).get('market_cap_unit'),expected)

    def test_unchanged_facts_refresh_raw_metadata_without_price_revision(self):
        m=self.module()
        html='<tr data-stock-code="005490" data-unit="원" data-date="2026-10-19"><span data-field="price">1100</span><span data-field="change">100</span><span data-field="pct">10</span><span data-field="market_cap">10000</span></tr>'
        before=m.parse_capitalization(html,'2026-10-19T18:00:00+09:00')['rows'][0]
        after=m.parse_capitalization(html.replace('data-unit="원"','data-unit="원" data-market-cap-unit="억원"'),'2026-10-19T18:10:00+09:00')['rows'][0]
        after['source_url']='https://finance.naver.com/item/main.naver?code=005490'
        with tempfile.TemporaryDirectory() as temp:
            db=str(Path(temp)/'test.db')
            payload={'indicators':[],'equities':[before],'warnings':[],'status':'partial'}
            with patch.object(m,'collect',return_value=payload):
                m.collect_and_save(None,db,lambda:False)
                payload['equities']=[after]
                m.collect_and_save(None,db,lambda:False)
            with closing(sqlite3.connect(db)) as cx:
                raw,captured,source=cx.execute('SELECT raw_json,captured_at,source_url FROM equity_rank_snapshots').fetchone()
                self.assertEqual(json.loads(raw)['market_cap_unit'],'억원')
                self.assertEqual(captured,after['captured_at'])
                self.assertEqual(source,after['source_url'])
                self.assertEqual(cx.execute('SELECT COUNT(*) FROM naver_revisions').fetchone()[0],0)

    def test_past_quote_age_never_creates_verified_close(self):
        m=self.module()
        base='<article data-mini-chart-id="KOSPI" data-unit="포인트" data-date="2026-10-16" %s><span data-field="value">110</span><span data-field="change">10</span><span data-field="pct">10</span>%s</article>'
        for attr,text,expected in [('', '',False),('', '장마감',True),('data-price-type="close"','',True),('data-session="closed"','',True)]:
            row=m.parse_indicators(base%(attr,text),'2026-10-19T08:30:00+09:00')['rows'][0]
            self.assertEqual(row['status'],'stale')
            self.assertEqual(json.loads(row['raw_json'])['close_verified'],expected)

    def test_collection_without_close_proof_is_partial_and_retryable(self):
        m=self.module()
        indicator=(HERE/'fixtures/naver_indicators_synthetic.html').read_text().replace('장마감','')
        equity=(HERE/'fixtures/naver_capitalization_synthetic.html').read_text()
        class Switch:
            def __init__(self,d):self.d=d
            def new_window(self,k):self.d.current_window_handle='ours';self.d.window_handles.append('ours')
            def window(self,k):self.d.current_window_handle=k
        class Driver:
            current_window_handle='original';current_url='about:blank'
            def __init__(self):self.window_handles=['original'];self.switch_to=Switch(self)
            def get(self,url):self.current_url=url
            @property
            def page_source(self):return indicator if self.current_url.endswith('/market') else equity
            def close(self):self.window_handles.remove(self.current_window_handle)
        with patch.object(m.time,'monotonic',side_effect=range(1000)),patch.object(m.time,'sleep'):
            result=m.collect(Driver(),lambda:False,lambda s:None)
        self.assertEqual(result['status'],'partial')
        self.assertTrue(any('close' in w.lower() for w in result['warnings']))

    def test_conflicting_duplicate_indicator_is_not_first_wins(self):
        m=self.module()
        template='<article data-mini-chart-id="KOSPI" data-unit="포인트" data-date="2026-10-16"><span data-field="value">%s</span><span data-field="change">10</span><span data-field="pct">10</span>장마감</article>'
        result=m.parse_indicators(template%'110'+template%'999','2026-10-19T08:30:00+09:00')
        self.assertTrue(all(r['status']=='unverified' for r in result['rows']))
        self.assertTrue(any('conflict' in w.lower() for w in result['warnings']))


if __name__ == '__main__': unittest.main()
