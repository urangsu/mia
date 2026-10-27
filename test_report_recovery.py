"""Synthetic-only recovery contracts; no browser, network, or shared lock."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

CAPTURE='2026-10-27T08:30:00+09:00'


class ReportRecoveryTests(unittest.TestCase):
    def test_old_successful_fdr_target_cannot_hide_new_naver_history(self):
        from report_model import build_context
        for state in ('complete','partial'):
            with self.subTest(state=state),tempfile.TemporaryDirectory() as folder:
                db=self.fixture(folder)
                with closing(sqlite3.connect(db)) as cx,cx:
                    cx.execute('UPDATE fdr_targets SET status=?',(state,))
                row=build_context(folder,captured_at=CAPTURE).tables['보고용_시장지표'][1]
                self.assertEqual(row[2],101)
                self.assertEqual(row[8],'close_pair_naver')

    def fixture(self, folder):
        import FastmarketsCollector_v3_4 as core
        import naver_markets, fdr_provider
        db=core.path_bundle(Path(folder))['db']
        with closing(sqlite3.connect(db)) as cx,cx:
            naver_markets.initialize_schema(cx)
            fdr_provider.initialize_schema(cx)
            for day,value in [('2026-10-23','100'),('2026-10-26','101')]:
                cx.execute('INSERT INTO market_indicators VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    ('KOSPI',day,CAPTURE,value,'1','1','points','','final','https://finance.naver.com/',json.dumps({'close_verified':True})))
            cx.execute('INSERT INTO fdr_targets VALUES(?,?,?,?,?)',('KOSPI','{}',CAPTURE,'failed','fixture fetch failed'))
        return db

    def test_calendar_failure_isolated_and_retry_recovers(self):
        from fdr_reporting import prepare
        from market_sessions import expected_pair
        def calendar(name,captured):
            if name=='XKRX':raise RuntimeError('fixture calendar unavailable')
            return expected_pair(name,captured)
        targets=[{'instrument_id':code} for code in ('KOSPI','NASDAQ')]
        with patch('fdr_reporting.expected_pair',side_effect=calendar):
            result=prepare([],targets,CAPTURE)
        self.assertEqual(set(result['pairs']),{'KOSPI','NASDAQ'})
        self.assertIsNone(result['pairs']['KOSPI']['previous_date'])
        self.assertEqual(result['pairs']['NASDAQ']['previous_date'],'2026-10-26')
        self.assertTrue(any('calendar' in w and 'KOSPI' in w for w in result['warnings']))
        self.assertEqual(prepare([],targets,CAPTURE)['pairs']['KOSPI']['previous_date'],'2026-10-26')

    def test_failed_fdr_preserves_verified_naver_pair_with_explicit_fallback(self):
        from report_model import build_context
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(folder)
            context=build_context(folder,captured_at=CAPTURE)
        row=context.tables['보고용_시장지표'][1]
        self.assertEqual(row[2],101)
        self.assertEqual(row[4],100)
        self.assertEqual(row[8],'close_pair_naver_fallback')
        self.assertTrue(any('fallback' in w and 'KOSPI' in w for w in context.warnings))
        self.assertIn('NAVER|KOSPI|',str(context._sheets['가격열설정']))

    def test_calendar_failure_does_not_block_context_or_hide_naver(self):
        from report_model import build_context
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(folder)
            with patch('fdr_reporting.expected_pair',side_effect=RuntimeError('fixture calendar unavailable')):
                context=build_context(folder,captured_at=CAPTURE)
        self.assertEqual(context.tables['보고용_시장지표'][1][2],101)
        self.assertTrue(context.snapshot_id)

    def test_calendar_failure_preserves_existing_quarantine_withdrawal(self):
        from fdr_reporting import prepare
        from fdr_provider import instruments
        q=dict(instrument_id='KOSPI',source_symbol=instruments([])['KOSPI'].symbol,
            market_date='2026-10-26',active=1)
        with patch('fdr_reporting.expected_pair',side_effect=RuntimeError('fixture unavailable')):
            result=prepare([],[{'instrument_id':'KOSPI'}],CAPTURE,quarantine=[q])
        self.assertEqual(result['quarantine'],[q])
        self.assertIn(('2026-10-26','FDR|KOSPI|points|Actual|MID'),result['withdrawn'])

    def test_failed_fdr_does_not_promote_unverified_naver_to_fallback(self):
        from report_model import build_context
        with tempfile.TemporaryDirectory() as folder:
            db=self.fixture(folder)
            with closing(sqlite3.connect(db)) as cx,cx:
                cx.execute("UPDATE market_indicators SET status='provisional'")
            context=build_context(folder,captured_at=CAPTURE)
        self.assertIsNone(context.tables['보고용_시장지표'][1][2])
        self.assertEqual(context.tables['보고용_시장지표'][1][8],'missing_history')

    def test_raw_equity_capture_visible_without_becoming_confirmed_cap(self):
        from report_model import build_context
        with tempfile.TemporaryDirectory() as folder:
            db=self.fixture(folder)
            with closing(sqlite3.connect(db)) as cx,cx:
                cx.execute('INSERT INTO equity_rank_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    ('005930',1,'fixture','2026-10-27',CAPTURE,'100','1','1','1234','원','KRW','provisional','fixture://cap',json.dumps({'market_cap_unit':'억원','close_verified':False})))
                cx.execute('INSERT INTO naver_raw_captures(captured_at,entity,entity_key,raw_json,reason) VALUES(?,?,?,?,?)',
                    (CAPTURE,'equities','005490','{}','undated fixture'))
            context=build_context(folder,captured_at=CAPTURE)
        rows=context.tables['증시_시총스냅샷']
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[1][6],'provisional')
        self.assertIn('수집시각',rows[0])
        self.assertEqual(rows[1][rows[0].index('수집시각')],CAPTURE)
        self.assertEqual(rows[1][rows[0].index('종가검증')],'미확정')
        self.assertEqual(len(context.tables['보고용_시총']),1)
        self.assertIn('NAVER_미검증캡처',context._sheets)

    def test_undated_raw_capture_visible_beside_confirmed_rows(self):
        from report_model import build_context
        with tempfile.TemporaryDirectory() as folder:
            db=self.fixture(folder)
            with closing(sqlite3.connect(db)) as cx,cx:
                for stamp,cap in [('2026-10-27T08:00:00+09:00','1200'),(CAPTURE,'1234')]:
                    row=dict(stock_code='005930',rank=1,name='captured fixture',market_date=None,
                        captured_at=stamp,price='100',market_cap=cap,status='unverified',
                        unit='원',currency='KRW',source_url='fixture://cap',
                        raw_json=json.dumps({'market_cap_unit':'억원','close_verified':False}))
                    cx.execute('INSERT INTO naver_raw_captures(captured_at,entity,entity_key,raw_json,reason) VALUES(?,?,?,?,?)',
                        (stamp,'equities','005930',json.dumps(row),'undated fixture'))
                cx.execute('INSERT INTO equity_rank_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    ('005930',1,'confirmed fixture','2026-10-26',CAPTURE,'100','1','1','1000','원','KRW','final','fixture://cap',json.dumps({'market_cap_unit':'억원','close_verified':True})))
            context=build_context(folder,captured_at=CAPTURE)
            selected=build_context(folder,captured_at=CAPTURE,series=['NAVER|005930|원|Actual|MID'])
        rows=context.tables['증시_시총스냅샷']
        self.assertEqual(len(rows),3)
        self.assertEqual({r[4] for r in rows[1:]},{1000,1234})
        live=next(r for r in rows[1:] if r[6]=='unverified')
        self.assertIsNone(live[3])
        self.assertEqual(live[-1],'미확정')
        self.assertEqual(context.tables['보고용_시총'][1][4],1000)
        self.assertEqual(len(selected.tables['증시_시총스냅샷']),3)


if __name__=='__main__':unittest.main()
