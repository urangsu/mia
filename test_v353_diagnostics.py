# -*- coding: utf-8 -*-
"""Offline regressions for v3.5.3 telemetry, FX, and report structure."""
import io
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout, closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import FastmarketsCollector_v3_4 as fm
from excel_secure import make_sheets
from smbs_rates import FXQuote, parse_row, save_rates, load_rates

class V353Tests(unittest.TestCase):
    def test_smbs_visible_html_example_20260928(self):
        q=parse_row(['2026.09.28','미국 달러 (USD)','1,352.00','8.00'],currency='USD',alt='환율하락 아이콘',classes='ico_down')
        self.assertEqual((q.quote_date,q.currency,q.rate,q.difference),('2026-09-28','USD','1352.00','-8.00'))

    def test_smbs_four_columns_one_per_currency_and_provenance_row(self):
        rows=[FXQuote('2026-09-28',code,str(i*100),'0',100 if code=='JPY' else 1)
              for i,code in enumerate(('USD','CNH','JPY','EUR'),1)]
        sheet=make_sheets([],[],rows)
        self.assertEqual(sheet['일별시세'][0],('고시일','USD','CNH','JPY(100)','EUR'))
        self.assertEqual(sheet['일별시세'][1],('','SMBS','SMBS','SMBS','SMBS'))
        self.assertEqual(sheet['일별시세'][2],('2026-09-28',100.0,200.0,300.0,400.0))
        self.assertEqual(sheet['환율원본'][0][3],'전일대비')

    def test_upsert_same_day_does_not_duplicate_or_revision(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'prices.sqlite3'
            quote=FXQuote('2026-09-28','USD','1352.00','-8.00',1)
            self.assertEqual(save_rates(p,[quote])['inserted'],1)
            self.assertEqual(save_rates(p,[quote])['unchanged'],1)
            self.assertEqual(len(load_rates(p)),1)
            with closing(sqlite3.connect(p)) as db, db:
                self.assertEqual(db.execute('select count(*) from fx_rate_revisions').fetchone()[0],0)

    def test_console_db_readonly_check_includes_actual_price(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'fastmarkets_prices_v3.sqlite3'
            with closing(sqlite3.connect(p)) as db, db:
                db.execute('CREATE TABLE prices (id INTEGER PRIMARY KEY)')
            save_rates(p,[FXQuote('2026-09-28','USD','1352.00','-8.00',1)])
            out=io.StringIO()
            with redirect_stdout(out):fm.inspect_stored_data(Path(td))
            self.assertIn('1352.00',out.getvalue())
            self.assertIn('-8.00',out.getvalue())

    def test_readonly_excel_check_does_not_touch_invalid_file(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'company.xlsx';p.write_bytes(b'DRM EXAMPLE; NO XLSX FORMAT')
            before=p.read_bytes()
            output=io.StringIO()
            with redirect_stdout(output):fm.inspect_excel_target(Path(td),p)
            self.assertIn('ZIP 형식: False',output.getvalue())
            self.assertEqual(before,p.read_bytes())

    def test_grid_dom_probe_and_actual_forecast_selector_present(self):
        self.assertIn('GRID_PROBE_JS',fm.ChromeSession.scrape.__code__.co_names)
        self.assertIn('headerIds',fm.GRID_PROBE_JS)
        self.assertIn('fui-price-calculation-type-dropdown',fm.SAMPLE_JS)
        self.assertIn('scrollbarthumbx',fm.SCROLL_INFO_JS)

    def test_async_native_horizontal_move_is_not_falsely_rejected(self):
        class Browser:
            def __init__(self):self.count=0
            def execute_script(self, script, *args):
                if script==fm.VISIBLE_GRID_JS:
                    self.count+=1
                    return 'before' if self.count<=2 else 'after'
                if script==fm.SCROLL_JS:return {'ok':True,'before':0,'after':159}
                raise AssertionError('unexpected JS requested')
        with patch.object(fm.time,'sleep',lambda _:None):
            self.assertTrue(fm.move_grid_scroll(Browser(),'fmwidget-1',0,'x',159))

if __name__=='__main__':unittest.main()
