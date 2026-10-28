"""Synthetic presentation regressions: never read company DBs or browser data."""
from dataclasses import replace
from pathlib import Path
from html.parser import HTMLParser
import tempfile
import unittest
from report_model import ReportContext, _freeze_tables


def sample_context():
    tables = {
        '보고용_금속시세': [('품목명','고시일','Mid','단위','구분','출처','코드','그룹','원본 조건'),
            ('전지급 탄산리튬','2026-10-27',13.7,'$/kg','Actual','https://dashboard.fastmarkets.com/en/','MB-LI-TEST','리튬','Battery grade, cif China'),
            ('블랙매스 Payable','2026-10-21',91,'% payable','Actual','Chart','MB-BM-TEST','블랙매스','Payable')],
        '보고용_환율': [('통화','고시일','매매기준율','전일대비','단위','출처'),
            ('JPY','2026-10-28',838.3,-1.53,'KRW/100 JPY','SMBS')],
        '보고용_시장지표': [('지표','시장일','수치','비교일','비교종가','전일대비','등락률(%)','단위','상태','출처'),
            ('KOSPI','2026-10-27',5638.34,'2026-10-26',5469.47,168.87,3.087502,'point','close_pair_naver','https://stock.naver.com/domestic/index/KOSPI/price'),
            ('US10Y','2026-10-27',4.993,'2026-10-26',4.986,.007,.140393,'%','calendar_unverified','javascript:alert(1)')],
        '증시_시총스냅샷': [('순위','종목명','코드','시장일','시가총액','단위','상태','출처','수집시각','종가검증'),
            (1,'삼성전자','005930',None,14133379,'억원','unverified','https://stock.naver.com/domestic/stock/005930/price','2026-10-28T08:30:00+09:00','미확정'),
            (1,'삼성전자','005930','2026-09-29',None,'미확인','stale','https://stock.naver.com/','2026-10-28T08:31:00+09:00','미확정'),
            (1,'삼성전자','005930',None,14000000,'억원','unverified','https://stock.naver.com/','2026-10-27T08:30:00+09:00','미확정')],
        '보고용_시총': [('순위','종목명','코드','시장일','시가총액','단위','상태','출처')],
        '보고용_종합': [('구분','종목','시장·고시일','수치','단위','상태','출처'),
            ('시총','005930',None,14133379,'억원','missing_prior_capture','https://stock.naver.com/')],
    }
    return ReportContext('synthetic-report','2026-10-28T08:31:00+09:00','TEST / 합성 데이터',
        _freeze_tables(tables),{},('FDR 연결 실패: proxy denied',),'fixture',None,'2026-10-28',{})


class ReportPresentationTests(unittest.TestCase):
    def render(self, context=None):
        from report_exports import export_html
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'report.html';export_html(context or sample_context(),path)
            return path.read_text()

    def test_default_light_and_top_theme_toggle(self):
        html=self.render()
        self.assertIn('data-theme="light"',html)
        self.assertIn('id="theme-toggle"',html)
        self.assertLess(html.index('id="theme-toggle"'),html.index('<h1'))
        self.assertIn('aria-pressed="false"',html)

    def test_all_warnings_and_raw_history_are_only_in_closed_bottom_details(self):
        html=self.render();body,audit=html.split('<details id="source-basis"',1)
        self.assertNotIn('proxy denied',body)
        self.assertNotIn('2026-09-29',body)
        self.assertIn('proxy denied',audit)
        self.assertIn('2026-09-29',audit)
        self.assertNotIn(' open',audit.split('>',1)[0])
        self.assertNotIn('content-visibility:visible',html)

    def test_main_tables_are_concise_and_names_link_to_sources(self):
        body=self.render().split('<details id="source-basis"',1)[0]
        for heading in ('출처','구분','상태','코드','시장일','수집시각','종가검증'):
            self.assertNotIn('>'+heading+'</th>',body)
        self.assertIn('href="https://dashboard.fastmarkets.com/en/"',body)
        self.assertIn('href="https://stock.naver.com/domestic/index/KOSPI/price"',body)
        self.assertNotIn('javascript:',body)
        self.assertNotIn('>005930<',body)

    def test_percent_one_decimal_no_scaling_raw_snapshot_preserved(self):
        context=sample_context();before=context.to_dict()
        body=self.render(context).split('<details id="source-basis"',1)[0]
        for value in ('+3.1%','91.0%','5.0%'):self.assertIn(value,body)
        self.assertNotIn('3.087502',body)
        self.assertNotIn('308.8%',body)
        self.assertEqual(context.to_dict(),before)

    def test_mixed_metal_dates_and_fx_100_jpy_basis_survive(self):
        body=self.render().split('<details id="source-basis"',1)[0]
        for value in ('2026.10.21','2026.10.27','2026.10.26','100 JPY','$/kg'):
            self.assertIn(value,body)

    def test_cap_snapshot_selects_latest_per_stock_not_history_or_duplicates(self):
        from report_presentation import presentation_tables
        tables=presentation_tables(sample_context())
        caps=[t for t in tables if t['kind']=='caps']
        self.assertEqual(sum(len(t['rows']) for t in caps),1)
        self.assertEqual(caps[0]['rows'][0][1]['text'],'삼성전자')
        self.assertIn('14,133,379',str(caps))
        self.assertNotIn('14,000,000',str(caps))
        self.assertIn('2026.10.28',caps[0]['subtitle'])
        self.assertIn('확정 종가 아님',caps[0]['subtitle'])

    def test_percentage_rounding_handles_zero_missing_and_nonfinite(self):
        from report_presentation import percentage
        self.assertEqual(percentage(-.00001),'0.0%')
        self.assertEqual(percentage(None),'—')
        self.assertEqual(percentage(float('nan')),'—')
        self.assertEqual(percentage(1.25),'+1.3%')

    def test_fmb_chart_source_links_to_its_workspace(self):
        context=replace(sample_context(),workspace_id='abcdefghijkl1234')
        body=self.render(context).split('<details id="source-basis"',1)[0]
        self.assertIn('href="https://dashboard.fastmarkets.com/w/abcdefghijkl1234/"',body)

    def test_quarantined_report_cap_is_not_replaced_with_raw_cap(self):
        context=sample_context();tables=dict(context.tables)
        tables['보고용_시총']=(tables['보고용_시총'][0],
            (1,'삼성전자','005930','2026-10-27',None,'미확인','quarantined','https://stock.naver.com/'))
        from report_presentation import presentation_tables
        projected=presentation_tables(replace(context,tables=_freeze_tables(tables)))
        cap=next(t for t in projected if t['kind']=='caps')
        self.assertEqual(cap['rows'][0][2]['text'],'—')

    def test_latest_cap_cohort_does_not_forward_fill_old_member_and_conflicts_blank(self):
        from report_presentation import _latest_caps
        rows=[{'코드':'A','시가총액':1,'수집시각':'2026-10-27T08:30:00+09:00'},
              {'코드':'B','시가총액':2,'수집시각':'2026-10-28T08:30:00+09:00'},
              {'코드':'B','시가총액':3,'수집시각':'2026-10-28T08:30:00+09:00'}]
        result=_latest_caps(rows)
        self.assertEqual([r['코드'] for r in result],['B'])
        self.assertIsNone(result[0]['시가총액'])

    def test_interest_rate_change_has_explicit_basis_points_not_bare_number(self):
        from report_presentation import presentation_tables
        market=next(t for t in presentation_tables(sample_context()) if t['kind']=='market')
        bond=next(r for r in market['rows'] if r[0]['text']=='미국 국채 10년')
        self.assertEqual(bond[3]['text'],'+0.7bp')

    def test_safe_links_reject_credentials_and_active_schemes(self):
        from report_presentation import safe_url
        for source in ('javascript:alert(1)','data:text/html,test','https://user:secret@example.com/','https://bad host.com/'):
            self.assertEqual(safe_url(source),'')
        self.assertEqual(safe_url('https://example.com/a / https://example.com/b'),'https://example.com/a')


if __name__=='__main__':unittest.main()
