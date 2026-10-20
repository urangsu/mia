"""Behavior regressions using temporary data; never opens a real browser."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import FastmarketsCollector_v3_4 as core
from smbs_rates import prepare_excel_series


class FunctionalCoreTests(unittest.TestCase):
    def test_settings_roundtrip_retains_source_and_output_options(self):
        with tempfile.TemporaryDirectory() as t:
            with patch.object(core, 'APP_HOME', Path(t)), patch.object(core, 'CONFIG_PATH', Path(t)/'config.json'):
                cfg = dict(core.config_load(), naver_enabled=False, fx_enabled=False,
                           report_dir='approved-reports', driver_path='', representative_symbols=['MB-LI-0029'])
                core.config_save(cfg)
                restored = core.config_load()
                self.assertIs(restored.get('naver_enabled'), False)
                self.assertIs(restored.get('fx_enabled'), False)
                self.assertEqual(restored.get('report_dir'), 'approved-reports')
                self.assertEqual(restored.get('representative_symbols'), ['MB-LI-0029'])

    def test_secrets_cannot_be_persisted_in_settings(self):
        with tempfile.TemporaryDirectory() as t:
            with patch.object(core, 'APP_HOME', Path(t)), patch.object(core, 'CONFIG_PATH', Path(t)/'config.json'):
                with self.assertRaises(ValueError):
                    core.config_save(dict(core.config_load(), password='synthetic-secret'))
                self.assertFalse(core.CONFIG_PATH.exists())

    def test_api_keys_and_credential_urls_cannot_be_persisted(self):
        from app_settings import save
        with tempfile.TemporaryDirectory() as t:
            for values in ({'api_key':'synthetic'},
                           {'workspace_url':'https://user:synthetic@dashboard.fastmarkets.com/'},
                           {'workspace_url':'HTTPS://user:synthetic@dashboard.fastmarkets.com/'},
                           {'workspace_url':' https://user:synthetic@dashboard.fastmarkets.com/'},
                           {'url':'https://example.invalid/?access_token=synthetic'}):
                with self.subTest(values=values),self.assertRaises(ValueError):
                    save(Path(t)/'config.json',values)

    def test_corrected_range_does_not_inherit_invalid_mid(self):
        with tempfile.TemporaryDirectory() as t:
            db = Path(t)/'synthetic.db'
            p = core.Price('MB-TEST-0001','2026-10-19','10','15','20',None,
                           'test/unit','Synthetic','Synthetic','Actual','Synthetic','one')
            diag = {'widget_count':1,'found_symbols':[p.symbol],'warnings':[]}
            core.save_sqlite(db,[p],[],diag)
            core.save_sqlite(db,[replace(p,low='30',mid=None,high='40')],[],diag)
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('SELECT low,mid,high FROM prices').fetchone(),('30',None,'40'))
                old = json.loads(cx.execute('SELECT old_values FROM price_revisions').fetchone()[0])
                self.assertEqual(old[:3],['10','15','20'])
                count = cx.execute('SELECT count(*) FROM price_revisions').fetchone()[0]
            core.save_sqlite(db,[replace(p,low='30',mid=None,high='40')],[],diag)
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('SELECT count(*) FROM price_revisions').fetchone()[0],count)

    def test_invalid_legacy_mid_is_quarantined_not_reported(self):
        p = core.Price('MB-TEST-0001','2026-10-19','30','15','40',None,
                       'test/unit','Synthetic','Synthetic','Actual','Synthetic','one')
        issues=[]; quarantined=[]
        rows=prepare_excel_series([p],[],issues=issues,quarantined=quarantined)
        key='FMB|MB-TEST-0001|test/unit|Actual|MID'
        self.assertNotIn(key,rows.get(p.date,{}))
        self.assertTrue(any(k==key for _,k,_ in quarantined))
        self.assertTrue(issues)

    def test_corrected_mid_withdrawal_reaches_existing_excel_plan(self):
        from report_model import build_context, make_workbook_sheets
        from excel_secure import quarantined_cells
        from ecm_excel_sync import build_plan
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t);db=core.path_bundle(folder)['db']
            p=core.Price('MB-TEST-0001','2026-10-19','10','15','20',None,
                         'test/unit','Synthetic','Synthetic','Actual','Synthetic','one')
            diag={'widget_count':1,'found_symbols':[p.symbol],'warnings':[]}
            core.save_sqlite(db,[p],[],diag)
            before=make_workbook_sheets(build_context(folder,end='2026-10-20'))
            core.save_sqlite(db,[replace(p,low='30',mid=None,high='40')],[],diag)
            after=make_workbook_sheets(build_context(folder,end='2026-10-20'))
            for tab in ('일별시세','일별요약','월별시세'):
                plan=build_plan(after[tab],after['가격열설정'],before[tab],before['가격열설정'],
                                period_type='monthly' if tab.startswith('월별') else 'daily',
                                clear_cells=quarantined_cells(after,tab))
                self.assertEqual(plan['stats']['cleared'],1,tab)
                self.assertIsNone(plan['edits'][0]['incoming'])
            core.save_sqlite(db,[replace(p,low='30',mid='35',high='40')],[],diag)
            recovered=make_workbook_sheets(build_context(folder,end='2026-10-20'))
            self.assertEqual(recovered['가격열설정'],before['가격열설정'])
            self.assertEqual(recovered['일별시세'][2][1],35)

if __name__ == '__main__':
    unittest.main()
