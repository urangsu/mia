"""External HTTP is injected; parsing, calendar, storage and revisions are real."""
from contextlib import closing
from datetime import datetime
from pathlib import Path
import importlib.util
import sqlite3
import tempfile
import unittest
import subprocess
import sys
import time
from unittest.mock import patch

CAPTURE='2026-10-22T08:30:00+09:00'


class ProviderTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('fdr_provider'),'FDR adapter missing')
        import fdr_provider
        return fdr_provider

    def test_explicit_sources_and_no_false_kr10y_or_cap_support(self):
        m=self.api();specs=m.instruments(['005490'])
        self.assertEqual(specs['005490'].symbol,'NAVER:005490')
        self.assertEqual(specs['KOSPI'].symbol,'NAVER:KOSPI')
        self.assertEqual(specs['GOLD'].kind,'continuous_future')
        self.assertNotIn('KR10Y',specs)
        with self.assertRaises(ValueError):m.instruments(['../../005490'])

    def test_close_not_adjusted_close_and_nan_not_zero(self):
        import pandas as pd
        m=self.api()
        frame=pd.DataFrame({'Close':[100,float('nan')],'Adj Close':[999,999]},index=pd.to_datetime(['2026-10-20','2026-10-21']))
        self.assertEqual(m.frame_records(frame),[{'date':'2026-10-20','close':'100.0'}])

    def test_calendar_filters_today_weekend_conflict_and_future(self):
        m=self.api();spec=m.instruments([])['SP500']
        rows=[{'date':d,'close':v} for d,v in [('2026-10-20','100'),('2026-10-21','101'),('2026-10-21','102'),('2026-10-18','99'),('2026-10-22','103')]]
        normalized,warnings=m.normalize(spec,rows,CAPTURE)
        self.assertEqual([r['market_date'] for r in normalized],['2026-10-20'])
        self.assertTrue(warnings)

    def test_db_noop_revisions_source_and_instrument_isolation(self):
        m=self.api();value=['101'];calls=[]
        def fetch(spec,start,end,cancelled,timeout):
            calls.append(spec.code)
            if spec.code=='NASDAQ':raise RuntimeError('upstream unavailable')
            return [{'date':'2026-10-20','close':'100'},{'date':'2026-10-21','close':value[0]}]
        with tempfile.TemporaryDirectory() as t:
            db=Path(t)/'test.db'
            a=m.collect_and_save(db,lambda:False,lambda _:None,captured_at=CAPTURE,fetcher=fetch)
            self.assertEqual(a['status'],'partial');self.assertGreater(a['saved'],0)
            self.assertIn('NASDAQ',a['missing'])
            calls.clear()
            m.collect_and_save(db,lambda:False,lambda _:None,captured_at=CAPTURE,fetcher=fetch)
            self.assertEqual(calls,['NASDAQ'])
            value[0]='102'
            m.collect_and_save(db,lambda:False,lambda _:None,captured_at=CAPTURE,fetcher=fetch,force=True)
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('SELECT count(*) FROM fdr_price_revisions').fetchone()[0],7)
                self.assertTrue(cx.execute("SELECT source_url FROM fdr_observations WHERE instrument_id='005490'").fetchone()[0].startswith('https://finance.naver.com/'))
                self.assertEqual(cx.execute("SELECT count(*) FROM sqlite_master WHERE name='market_indicators'").fetchone()[0],0)

    def test_cancellation_before_fetch_has_no_price_writes(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as t:
            db=Path(t)/'test.db'
            result=m.collect_and_save(db,lambda:True,captured_at=CAPTURE,fetcher=lambda *a: self.fail('network after cancel'))
            self.assertEqual(result['status'],'cancelled')
            with closing(sqlite3.connect(db)) as cx:self.assertEqual(cx.execute('SELECT count(*) FROM fdr_observations').fetchone()[0],0)

    def test_missing_latest_session_cannot_be_replaced_with_older_pair(self):
        m=self.api();spec=m.instruments([])['KOSPI']
        rows,_=m.normalize(spec,[{'date':'2026-10-19','close':'99'},{'date':'2026-10-20','close':'100'}],CAPTURE)
        self.assertFalse(m.has_expected_pair(spec,rows,CAPTURE))

    def test_owned_worker_timeout_and_cancel_are_reaped(self):
        m=self.api();owned=[];launch=subprocess.Popen
        def factory(*args,**kwargs):
            p=launch([sys.executable,'-c','import time; time.sleep(30)'],**kwargs)
            owned.append(p);return p
        with patch.object(m.subprocess,'Popen',side_effect=factory):
            with self.assertRaises(TimeoutError):
                m.fetch_history(m.instruments([])['SP500'],'2026-10-01','2026-10-22',lambda:False,.1)
            with self.assertRaises(InterruptedError):
                m.fetch_history(m.instruments([])['SP500'],'2026-10-01','2026-10-22',lambda:True,1)
        self.assertTrue(all(p.poll() is not None for p in owned))

    def test_csv_noop_preserves_file_and_quarantine_column(self):
        m=self.api()
        with tempfile.TemporaryDirectory() as t:
            db=Path(t)/'test.db';path=Path(t)/'public.csv'
            m.collect_and_save(db,lambda:False,lambda _:None,captured_at=CAPTURE,
                fetcher=lambda *a:[{'date':'2026-10-20','close':'100'},{'date':'2026-10-21','close':'101'}])
            m.export_csv(db,path);before=path.stat().st_mtime_ns
            m.export_csv(db,path)
            self.assertEqual(path.stat().st_mtime_ns,before)
            self.assertIn('quarantined',path.read_text(encoding='utf-8-sig'))


if __name__=='__main__':unittest.main()
