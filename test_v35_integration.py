"""v3.5 no-network regression contracts: durable DB, secure Excel dispatch and GUI settings."""
from __future__ import annotations
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_v33 import m, price
import smbs_rates as fx
import excel_secure as sec
from contextlib import closing

class V35IntegrationTests(unittest.TestCase):
    def test_workspace_url_validation(self):
        u='https://dashboard.fastmarkets.com/w/moCxu7v7xQKU99uHbd6LRv/some-path'
        self.assertEqual(m.verify_workspace_url(u)[1],'moCxu7v7xQKU99uHbd6LRv')
        for bad in ('https://evil.example/w/moCxu7v7xQKU99uHbd6LRv/',
                    'http://dashboard.fastmarkets.com/w/moCxu7v7xQKU99uHbd6LRv/',
                    'https://dashboard.fastmarkets.com/w/foobar',
                    u+'?token=secret'):
            with self.subTest(url=bad),self.assertRaises(ValueError):m.verify_workspace_url(bad)

    def test_fmb_idempotent_storage_and_one_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'test.sqlite'
            diag={'widget_count':1,'found_symbols':['MB-LI-0029'],'warnings':[]}
            m.save_sqlite(db,[price()],[],diag)
            with closing(sqlite3.connect(db)) as cx:
                cx.execute("UPDATE prices SET collected_at='2000-01-01 00:00:00'");cx.commit()
            m.save_sqlite(db,[price()],[],diag)
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('SELECT COUNT(*) FROM prices').fetchone()[0],1)
                self.assertEqual(cx.execute('SELECT collected_at FROM prices').fetchone()[0],'2000-01-01 00:00:00')
                self.assertEqual(cx.execute('SELECT COUNT(*) FROM price_revisions').fetchone()[0],0)
            m.save_sqlite(db,[price(mid='16')],[],diag)
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('SELECT COUNT(*) FROM prices').fetchone()[0],1)
                self.assertEqual(cx.execute('SELECT COUNT(*) FROM price_revisions').fetchone()[0],1)

    def test_legacy_workspace_visible_and_new_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'fastmarkets_prices_v3.sqlite3'
            d={'widget_count':1,'found_symbols':[],'warnings':[]}
            with patch.object(m,'current_workspace',return_value=(m.WORKSPACE_URL,'LEGACY-OLD')):
                m.save_sqlite(db,[price(date='2025-12-30',mid='10'),price(date='2026-01-02',mid='11')],[],d)
            with patch.object(m,'current_workspace',return_value=(m.WORKSPACE_URL,'NEW-WORKSPACE')):
                m.save_sqlite(db,[price(date='2026-01-02',mid='12')],[],d)
                combined=m.load_prices(Path(tmp))
            self.assertEqual([(p.date,p.mid) for p in combined],[('2026-01-02','12'),('2025-12-30','10')])
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('SELECT COUNT(*) FROM prices').fetchone()[0],3)

    def test_fx_reimport_not_duplicate_and_revisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'prices.sqlite'
            q=fx.FXQuote('2026-12-31','USD','1500.00','-1.00',1)
            a=fx.FXQuote('2027-01-02','USD','1510.00','10.00',1)
            self.assertEqual(fx.save_rates(db,[q,a])['inserted'],2)
            self.assertEqual(fx.save_rates(db,[q,a])['unchanged'],2)
            self.assertEqual(fx.save_rates(db,[fx.FXQuote('2027-01-02','USD','1520.00','20.00',1)])['updated'],1)
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('SELECT COUNT(*) FROM fx_rates').fetchone()[0],2)
                self.assertEqual(cx.execute('SELECT COUNT(*) FROM fx_rate_revisions').fetchone()[0],1)
            series=fx.prepare_excel_series([] ,fx.load_rates(db))
            self.assertEqual(sorted(series),['2026-12-31','2027-01-02'])

    def test_excel_security_no_guess_or_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'drm.xlsx';f.write_bytes(b'ENCRYPTED-WRAPPED-FILE')
            self.assertFalse(sec.is_plain_xlsx(f))
            self.assertEqual(f.read_bytes(),b'ENCRYPTED-WRAPPED-FILE')

    def test_excel_com_used_for_windows_without_openpyxl(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            with patch.object(m,'IS_WINDOWS',True), patch.object(sec,'write_com_sheets',return_value=folder/'out.xlsx') as mocked:
                actual=m.export_workbook(folder,output_path=folder/'out.xlsx')
            mocked.assert_called_once()
            self.assertEqual(actual,folder/'out.xlsx')

    def test_summary_after_2026_year_end(self):
        quotes=[fx.FXQuote('2026-12-31','JPY','900','-1',100),fx.FXQuote('2027-01-04','JPY','910','10',100)]
        sheets=sec.make_sheets([],[],quotes)
        self.assertEqual([r[0] for r in sheets['일별시세'][2:]],['2026-12-31','2027-01-04'])
        self.assertEqual([r[0] for r in sheets['월별시세'][2:]],['2026-12','2027-01'])

    def test_ecm_name_and_search_config_support(self):
        import ecm_automation as e
        self.assertEqual(e.run_ecm_control.__defaults__,(None,None))
        self.assertEqual(e._is_target_link.__defaults__,(None,))


    def test_secure_excel_prices_are_numeric_and_raw_strings_remain_text(self):
        self.assertEqual(sec.excel_value('Daily','mid','1532.2000'),1532.2)
        self.assertEqual(sec.excel_value('Latest','low','0.010'),0.01)
        self.assertEqual(sec.excel_value('일별시세','FX_USD','1422.70'),1422.7)
        self.assertEqual(sec.excel_value('RawData','low','1532.2000'),'1532.2000')
        self.assertEqual(sec.excel_value('RawData','description','=HYPERLINK("x")'), "'=HYPERLINK(\"x\")")
        self.assertIsNone(sec.excel_value('일별시세','FX_USD',None))
        with self.assertRaises(sec.SecureExcelError):sec.excel_value('Daily','mid','데이터 없음')

    def test_com_sheet_status_and_averaging_excludes_daily_differences(self):
        qs=[fx.FXQuote('2026-12-30','USD','1420','-2',1),
            fx.FXQuote('2026-12-31','USD','1430','10',1)]
        sheets=sec.make_sheets([],[],qs)
        self.assertIn('수집현황',sheets)
        heads=list(sheets['월별시세'][0]);avgrow=list(sheets['월별시세'][2])
        self.assertFalse(any('전일대비' in h for h in heads))
        rateidx=next(i for i,h in enumerate(heads) if h == 'USD')
        self.assertEqual(avgrow[rateidx],1425.0)
        self.assertEqual(sheets['환율원본'][1][3],-2.0)

    def test_horizontal_scroll_has_thumb_backup_and_visible_column_fingerprint(self):
        self.assertIn('scrollbar-x [scrollbarthumbx]',m.SCROLL_INFO_JS)
        self.assertIn('getClientRects',m.VISIBLE_GRID_JS)
        self.assertIn('VISIBLE_GRID_JS',m.move_grid_scroll.__code__.co_names)


    def test_all_workspace_csv_preserves_old_workspace_without_breaking_legacy_export(self):
        import csv
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            db=folder/'fastmarkets_prices_v3.sqlite3'
            d={'widget_count':1,'found_symbols':[],'warnings':[]}
            with patch.object(m,'current_workspace',return_value=(m.WORKSPACE_URL,'OLD')):
                m.save_sqlite(db,[price(date='2025-01-02',mid='11')],[],d)
            with patch.object(m,'current_workspace',return_value=(m.WORKSPACE_URL,'NEW')):
                m.save_sqlite(db,[price(date='2026-01-02',mid='12')],[],d)
                m.export_files(folder)
            with (folder/'fastmarkets_all_workspaces.csv').open(encoding='utf-8-sig') as h:
                rows=list(csv.DictReader(h))
            self.assertEqual({r['workspace_id'] for r in rows},{'OLD','NEW'})
            with (folder/'fastmarkets_prices_v3.csv').open(encoding='utf-8-sig') as h:
                legacy=list(csv.DictReader(h))
            self.assertEqual(len(legacy),1)
            self.assertNotIn('workspace_id',legacy[0])

    def test_installer_does_not_require_openpyxl_for_windows(self):
        import inspect
        source=inspect.getsource(m.install_packages)
        self.assertIn('if not IS_WINDOWS',source)



    def test_fx_identical_numeric_with_different_precision_no_false_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'price.sqlite'
            self.assertEqual(fx.save_rates(db,[fx.FXQuote('2026-10-16','USD','1348.50','-2.00',1)])['inserted'],1)
            self.assertEqual(fx.save_rates(db,[fx.FXQuote('2026-10-16','USD','1348.5','-2',1)])['unchanged'],1)
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('SELECT COUNT(*) FROM fx_rate_revisions').fetchone()[0],0)

if __name__=='__main__':unittest.main()
