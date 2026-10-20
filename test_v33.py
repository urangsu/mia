"""Offline contracts. No site, browser, WinVault, or UI interactions."""
import csv
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
from contextlib import closing

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location('fm33_test', ROOT/'FastmarketsCollector_v3_4.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


def price(**kw):
    p = m.Price('MB-LI-0029', '2026-10-15', '14', '14.8', '15.6', '-5.13',
                '$/kg', 'Lithium carbonate', 'Lithium', 'Actual', 'AG Grid', 'view')
    return replace(p, **kw)


class NewContracts(unittest.TestCase):
    def test_partial_revision_replaces_price_tuple_without_stale_fields(self):
        with tempfile.TemporaryDirectory() as t:
            db = Path(t)/'x.db'
            diag = {'widget_count':1, 'found_symbols':['MB-LI-0029'], 'warnings':[]}
            m.save_sqlite(db, [price()], [], diag)
            m.save_sqlite(db, [price(low=None, mid='15', high=None, change_pct=None)], [], diag)
            with closing(sqlite3.connect(db)) as cx:
                row = cx.execute('select low,mid,high,change_pct from prices').fetchone()
            self.assertEqual(row, (None,'15',None,None))

    def test_revision_audit(self):
        with tempfile.TemporaryDirectory() as t:
            db = Path(t)/'x.db'
            diag = {'widget_count':1, 'found_symbols':[], 'warnings':[]}
            m.save_sqlite(db, [price()], [], diag)
            m.save_sqlite(db, [price(mid='15')], [], diag)
            m.save_sqlite(db, [price(mid='15')], [], diag)
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('select count(*) from price_revisions').fetchone()[0], 1)

    def test_csv_failure_preserves_existing_export(self):
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t)
            target = m.path_bundle(folder)['csv']
            target.write_text('previous', encoding='utf-8')
            diag = {'widget_count':1, 'found_symbols':[], 'warnings':[]}
            m.save_sqlite(m.path_bundle(folder)['db'], [price()], [], diag)
            with patch.object(m.csv, 'writer', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):m.export_files(folder)
            self.assertEqual(target.read_text(), 'previous')

    def test_live_driver_is_revalidated_before_use(self):
        session = m.ChromeSession()
        session.driver = MagicMock(window_handles=['one'])
        with patch.object(session, '_validate_listener', side_effect=m.PortOwnershipError('wrong profile')):
            with self.assertRaises(m.PortOwnershipError):session.connect()

    def test_workspace_url_without_dom_not_logged_in(self):
        session = m.ChromeSession()
        session.driver = MagicMock()
        session.driver.current_url = m.WORKSPACE_URL
        session.driver.window_handles = ['workspace']
        session.driver.execute_script.return_value = False
        with patch.object(session, 'select_domain_tab', return_value=True):
            self.assertFalse(session.workspace_is_open())

    def test_merge_title_conflict_is_not_silent(self):
        a = {'headers':[], 'grids':[{'index':0, 'rows':[{'index':0, 'cells':[
            {'colId':'MB-LI-0029-mid','text':'14.8','title':'14.80'}]}]}]}
        b = {'headers':[], 'grids':[{'index':0, 'rows':[{'index':0, 'cells':[
            {'colId':'MB-LI-0029-mid','text':'14.8','title':'15.80'}]}]}]}
        errors = []
        m.merge_samples(a, b, errors)
        self.assertTrue(errors)

    def test_latest_does_not_relabel_old_or_forecast(self):
        rows = m.latest_quotes([price(), price(price_mode='Forecast', date='2026-10-17'),
                                price(date='2026-10-16', mid='15')], today=date(2026,10,17))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['date'], '2026-10-16')
        self.assertEqual(rows[0]['freshness'], '前日以前')

    def test_coverage_reports_black_mass_payables(self):
        report = m.coverage_report([price()], [{'codes':['MB-LI-0029','MB-BMS-0001'],
            'description_by_code':{'MB-LI-0029':'Lithium carbonate','MB-BMS-0001':'Nickel payable'},
            'widget':'BM', 'scroll_caps':[]}])
        self.assertIn('MB-BMS-0001', report['missing_prices'])
        self.assertFalse(report['complete'])

    def test_import_csv_and_dom_comparison(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t)/'official.csv'
            with f.open('w', newline='', encoding='utf-8-sig') as fp:
                w = csv.DictWriter(fp, fieldnames=['symbol','date','low','mid','high','unit','description','price_mode','change_pct'])
                w.writeheader();w.writerow({'symbol':'MB-LI-0029','date':'2026-10-15',
                    'low':'14','mid':'14.80','high':'15.6','unit':'$/kg',
                    'description':'Lithium carbonate','price_mode':'Actual','change_pct':'-5.13'})
            prices, report = m.read_official_csv(f)
            self.assertEqual(len(prices), 1)
            self.assertEqual(m.compare_sources(prices,[price()])['matched'], 1)
            self.assertEqual(m.compare_sources(prices,[price(mid='20')])['mismatched'], 1)

    def test_ambiguous_csv_date_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t)/'official.csv'
            f.write_text('symbol,date,mid,unit\nMB-LI-0029,03/04/2026,14,$/kg\n')
            with self.assertRaises(ValueError):m.read_official_csv(f)


class ECMContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ecm_automation
        cls.e = ecm_automation

    def link(self, name='(리뉴얼)금속 가격  현황.xlsx', rect=(100,200,900,220), kind='HyperlinkControl'):
        c = MagicMock()
        c.Name, c.ControlTypeName, c.IsOffscreen = name, kind, False
        c.BoundingRectangle.left, c.BoundingRectangle.top = rect[:2]
        c.BoundingRectangle.right, c.BoundingRectangle.bottom = rect[2:]
        return c

    def test_reject_row_and_duplicate_links(self):
        row = self.link(kind='DataItemControl')
        a, b = self.link(), self.link()
        with patch.object(self.e, '_controls', return_value=iter([row,a])):
            self.assertIs(self.e._target_file(MagicMock(),timeout=0), a)
        with patch.object(self.e, '_controls', return_value=iter([a,b])):
            with self.assertRaises(RuntimeError):self.e._target_file(MagicMock(),timeout=0)

    def test_point_uses_left_text_region_not_row_center(self):
        x,y = self.e.link_click_point((100,200,900,220))
        self.assertLess(x, 250)
        self.assertTrue(200 < y < 220)

    def test_edge_debug_process_is_never_candidate(self):
        self.assertFalse(self.e.is_normal_edge_process({'Name':'msedge.exe',
            'CommandLine':'msedge.exe --remote-debugging-port=9337 --user-data-dir=C:/POSPIA'}))
        self.assertTrue(self.e.is_normal_edge_process({'Name':'msedge.exe','CommandLine':'msedge.exe'}))
        self.assertFalse(self.e.is_normal_edge_process({'Name':'chrome.exe','CommandLine':'chrome.exe'}))
        self.assertFalse(self.e.is_normal_edge_process({'Name':'msedge.exe','CommandLine':None}))

    def test_verified_link_gets_single_left_offset_double_click(self):
        item=self.link();backend=MagicMock()
        backend.ControlFromPoint.return_value=item
        backend.ControlsAreSame.return_value=True
        with patch.object(self.e,'auto',backend):self.e._double_click_link(item,lambda x:None)
        item.DoubleClick.assert_called_once()
        self.assertLess(item.DoubleClick.call_args.kwargs['x'],100)

    def test_open_failure_does_not_click_again(self):
        with patch.object(self.e,'_open_documents',return_value=set()):
            with self.assertRaisesRegex(RuntimeError,'중복 클릭'):self.e._wait_open(set(),timeout=0)

    def test_repeated_open_is_skipped(self):
        with patch.object(self.e,'_locate_ecm'),patch.object(self.e,'_activate'), \
             patch.object(self.e,'_open_important_contents'),patch.object(self.e,'_input_search'), \
             patch.object(self.e,'_submit_search'),patch.object(self.e,'_target_file',return_value=self.link()), \
             patch.object(self.e,'_open_documents',return_value={('Excel',1,'file')}), \
             patch.object(self.e,'_double_click_link') as click:
            self.assertIn('중복',self.e.run_ecm_control(lambda s:None))
            click.assert_not_called()

    def test_wrong_hit_never_double_clicks(self):
        item = self.link()
        wrong = self.link(name='Other.xlsx')
        backend = MagicMock()
        backend.ControlsAreSame.return_value = False
        backend.ControlFromPoint.return_value = wrong
        with patch.object(self.e,'auto',backend):
            with self.assertRaises(RuntimeError):self.e._double_click_link(item,lambda x:None)
        item.DoubleClick.assert_not_called()
        backend.DoubleClick.assert_not_called()

    def test_search_focus_requires_identity_not_name(self):
        a,b=self.link(kind='EditControl'),self.link(kind='EditControl',rect=(100,400,900,420))
        a.AutomationId=b.AutomationId=''
        self.assertFalse(self.e._same_edit(a,b))


if __name__ == '__main__':unittest.main(verbosity=2)
