"""Synthetic regressions for fresh setup, quarantine propagation and GUI recovery."""
import ast
import os
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing, contextmanager
from dataclasses import replace
from datetime import date
from pathlib import Path
from queue import Queue, Empty
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import FastmarketsCollector_v3_4 as core
import ecm_excel_sync as ecm
import excel_secure
import pipeline_v37
import report_model
import storage_runtime
from smbs_rates import FXQuote, save_rates


KEY = 'FMB|MB-LI-0029|$/kg|Actual|MID'
DAY = '2026-10-16'


def price(**changes):
    return replace(core.Price('MB-LI-0029', DAY, '10', '15', '20', None,
                   '$/kg', 'Lithium carbonate', 'Lithium', 'Actual', 'AG Grid', 'one'), **changes)


def store(folder, prices):
    core.save_sqlite(core.path_bundle(Path(folder))['db'], prices, [],
                     {'widget_count': 1, 'found_symbols': ['MB-LI-0029'], 'warnings': []})


def sheets(folder):
    return report_model.make_workbook_sheets(report_model.build_context(folder, end='2026-10-19'))


class FreshSetupTests(unittest.TestCase):
    def test_real_scrape_saves_first_prices_after_v37_initialization(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            storage_runtime.migrate_database(core.path_bundle(folder)['db'])
            widget = dict(id='test', title='Lithium', gridCount=0)
            sample = dict(title='Lithium', mode='Actual', directCodes=['MB-LI-0029'], unit='$/kg',
                          grids=[dict(index='0', rows=[dict(index=0, cells=[
                              dict(colId='date', text=date.today().isoformat()),
                              dict(colId='MB-LI-0029-mid', text='15')])])])
            driver = MagicMock(window_handles=['test'], current_window_handle='test')
            driver.execute_script.side_effect = lambda script, *args: (
                {'widgets': [widget], 'url': core.WORKSPACE_URL} if script == core.INVENTORY_JS else sample)
            browser = core.ChromeSession(); browser.driver = driver
            with patch.object(browser, 'connect', return_value=driver), \
                 patch.object(browser, 'workspace_is_open', return_value=True), \
                 patch.object(browser, '_validate_listener'), patch.object(core.time, 'sleep'):
                rows, _ = browser.scrape(31, folder, threading.Event(), defer_export=True)
            self.assertEqual(len(rows), 1)
            self.assertEqual(core.stored_symbols(folder), ['MB-LI-0029'])
            self.assertEqual(len(core.load_prices(folder)), 1)

    def test_corrupt_existing_instruments_schema_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            with closing(sqlite3.connect(core.path_bundle(Path(folder))['db'])) as cx, cx:
                cx.execute('CREATE TABLE instruments(wrong_column TEXT)')
            with self.assertRaises(sqlite3.OperationalError):
                core.stored_symbols(Path(folder))


class QuarantineTests(unittest.TestCase):
    def plan(self, source, target, tab='일별시세'):
        return ecm.build_plan(source[tab], source['가격열설정'], target[tab], target['가격열설정'],
                              period_type='monthly' if tab.startswith('월별') else 'daily',
                              clear_cells=excel_secure.quarantined_cells(source, tab))

    def test_conflict_clears_old_values_but_retains_catalog_and_recovers(self):
        with tempfile.TemporaryDirectory() as folder:
            store(folder, [price()]); before = sheets(folder)
            store(folder, [price(mid='99', view_key='two')]); conflicted = sheets(folder)
            self.assertIn(KEY, [r[0] for r in conflicted['가격열설정'][1:]])
            self.assertEqual(conflicted['일별시세'][2][1], None)
            self.assertIn(('일별시세', DAY, KEY), [r[:3] for r in conflicted['보류셀'][1:]])
            for tab in ('일별시세', '일별요약', '월별시세'):
                plan = self.plan(conflicted, before, tab)
                self.assertEqual(plan['stats']['cleared'], 1)
                self.assertEqual(plan['edits'][0]['incoming'], None)
                self.assertEqual(plan['edits'][0]['decision'], 'quarantine')
            counts = self.plan(conflicted, before, '월별건수')
            self.assertEqual(counts['edits'][0]['incoming'], 0)
            store(folder, [price(view_key='two')]); recovered = sheets(folder)
            plan = self.plan(recovered, conflicted)
            self.assertFalse(plan['new_columns'])
            self.assertEqual(plan['edits'][0]['col'], 2)
            self.assertEqual(plan['edits'][0]['incoming'], 15)

    def test_only_conflicted_cell_clears_and_other_month_values_survive(self):
        with tempfile.TemporaryDirectory() as folder:
            store(folder, [price(), price(date='2026-10-15', mid='12')]); before = sheets(folder)
            store(folder, [price(mid='99', view_key='two')]); after = sheets(folder)
            # A manual column physically between A and LC must never be selected.
            before['일별시세'] = [tuple([r[0], 'Manual' if i == 0 else 'USER' if i == 1 else 123]+list(r[1:]))
                                      for i, r in enumerate(before['일별시세'])]
            plan = self.plan(after, before)
            self.assertEqual([(e['date'], e['col'], e['incoming']) for e in plan['edits']], [(DAY, 3, None)])
            self.assertEqual(after['월별시세'][2][1], 12)
            self.assertEqual(after['월별건수'][2][1], 1)
            self.assertFalse(excel_secure.quarantined_cells(after, '월별시세'))

    def test_missing_without_explicit_quarantine_preserves_prior_value(self):
        rows = [('고시일', 'LC'), ('', 'FMB'), (DAY, None)]
        old = rows[:2]+[(DAY, 15)]
        catalog = [('key', 'name'), (KEY, 'LC')]
        plan = ecm.build_plan(rows, catalog, old, catalog)
        self.assertFalse(plan['edits'])
        self.assertEqual(plan['stats']['missing_source'], 1)

    def test_fx_conflict_and_naver_month_merge_keep_clear_directives(self):
        from test_v37_reports import ReportTests
        with tempfile.TemporaryDirectory() as folder:
            ReportTests().fixture(folder)
            db = core.path_bundle(Path(folder))['db']
            save_rates(db, [FXQuote(DAY, 'USD', '1400', '1', 1, 'SMBS')])
            before = sheets(folder)
            save_rates(db, [FXQuote(DAY, 'USD', '999', '1', 1, 'other')])
            after = sheets(folder)
            self.assertEqual(after['월별시세'][2][1], None)
            self.assertEqual(after['월별건수'][2][1], 0)
            for tab in ('일별시세', '일별요약', '월별시세'):
                plan = self.plan(after, before, tab)
                cleared = [e for e in plan['edits'] if e['decision'] == 'quarantine']
                self.assertEqual([e['key'] for e in cleared], ['FX_USD_KRW_per_1'])

    def test_ecm_preview_applies_clears_and_rechecks_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            store(folder, [price()]); before = sheets(folder)
            store(folder, [price(mid='99', view_key='two')])
            wb = MagicMock(Name='test.xlsx', FullName='C:/ECM/test.xlsx', Date1904=False)
            ws = wb.Worksheets.return_value; ws.ProtectContents = False
            ws.UsedRange.Column = 1; ws.UsedRange.Row = 1
            ws.UsedRange.Columns.Count = 2; ws.UsedRange.Rows.Count = 3
            cell = MagicMock(); cell.HasFormula = False; cell.Value2 = 15
            ws.Cells.return_value = cell
            @contextmanager
            def attached(*args, **kwargs): yield wb
            with patch.object(ecm, '_attached_excel', attached), \
                 patch.object(ecm, '_read_matrix', return_value=before['일별요약']), \
                 patch.object(ecm, '_read_catalog', return_value=before['가격열설정']):
                plan = ecm.prepare_ecm_plan(folder, 'test.xlsx', log=lambda x: None)
                self.assertEqual(plan['stats']['cleared'], 1)
                with patch('com_updates.put_blocks', side_effect=lambda ws, edits, history: setattr(cell, 'Value2', None)):
                    result = ecm.apply_ecm_plan(folder, 'test.xlsx', plan, log=lambda x: None)
                self.assertEqual(result['applied'], 1)
                self.assertFalse(result['server_verified'])
                wb.Save.assert_called_once()
                store(folder, [price(view_key='two')])
                with self.assertRaisesRegex(ecm.ECMBlocked, '달라졌습니다'):
                    ecm.apply_ecm_plan(folder, 'test.xlsx', plan, log=lambda x: None)

    def test_ecm_quarantine_does_not_overwrite_formula(self):
        with tempfile.TemporaryDirectory() as folder:
            store(folder, [price()]); before = sheets(folder)
            store(folder, [price(mid='99', view_key='two')])
            wb = MagicMock(Name='test.xlsx', FullName='C:/ECM/test.xlsx', Date1904=False)
            ws = wb.Worksheets.return_value; ws.ProtectContents = False
            ws.Cells.return_value.HasFormula = True
            @contextmanager
            def attached(*args, **kwargs): yield wb
            with patch.object(ecm, '_attached_excel', attached), \
                 patch.object(ecm, '_read_matrix', return_value=before['일별요약']), \
                 patch.object(ecm, '_read_catalog', return_value=before['가격열설정']):
                plan = ecm.prepare_ecm_plan(folder, 'test.xlsx', log=lambda x: None)
                with self.assertRaisesRegex(ecm.ECMBlocked, '수식 보호'):
                    ecm.apply_ecm_plan(folder, 'test.xlsx', plan, log=lambda x: None)
                wb.Save.assert_not_called()

    def test_local_com_writer_clears_then_recovers_in_same_user_column_layout(self):
        """Run the complete staging writer against an in-memory COM double."""
        with tempfile.TemporaryDirectory() as folder:
            store(folder, [price()]); before = sheets(folder)
            store(folder, [price(mid='99', view_key='two')]); after = sheets(folder)
            # Limit the COM double to the production daily/catalog/audit paths.
            after = {k: after[k] for k in ('일별시세', '가격열설정', '보류셀')}
            before['일별시세'] = [('고시일', 'Manual', 'LC'), ('', 'USER', 'FMB'), (DAY, '=1+1', 15)]
            pages = {}
            class Cell:
                def __init__(self, value=None):
                    self.Value2 = value; self.HasFormula = isinstance(value, str) and value.startswith('=')
                @property
                def Value(self): return self.Value2
            class Range:
                def __init__(self, a, b):
                    self.a=a; self.b=b; self.Font=MagicMock(); self.Interior=MagicMock()
                @property
                def Value2(self):
                    return tuple(tuple(pages[self.a[0]].cell(r,c).Value2 for c in range(self.a[2],self.b[2]+1))
                                 for r in range(self.a[1],self.b[1]+1))
                @Value2.setter
                def Value2(self, values):
                    for r,row in enumerate(values,self.a[1]):
                        for c,value in enumerate(row,self.a[2]): pages[self.a[0]].cell(r,c).Value2=value
                def AutoFilter(self): pass
            for name in after:
                ws=MagicMock(); ws.Name=name; ws.ProtectContents=False; ws.ListObjects.Count=0
                cells={}
                for r,row in enumerate(before.get(name, []),1):
                    for c,value in enumerate(row,1): cells[r,c]=Cell(value)
                def cell(r,c, cells=cells): return cells.setdefault((r,c),Cell())
                ws.cell=cell
                # Cell coordinates are kept separately for Range endpoints.
                ws.Cells.side_effect=lambda r,c,n=name:(n,r,c)
                ws.Range.side_effect=lambda a,b:Range(a,b)
                pages[name]=ws
            # Production uses both scalar Cells and Range endpoints. Coordinate
            # wrappers expose scalar attributes while retaining tuple indexing.
            class Endpoint(tuple):
                @property
                def Value2(self): return pages[self[0]].cell(self[1],self[2]).Value2
                @Value2.setter
                def Value2(self, value): pages[self[0]].cell(self[1],self[2]).Value2=value
                @property
                def Value(self): return self.Value2
                @property
                def HasFormula(self): return pages[self[0]].cell(self[1],self[2]).HasFormula
            for name,ws in pages.items():
                ws.Cells.side_effect=lambda r,c,n=name:Endpoint((n,r,c))
            wb=MagicMock(); wb.ReadOnly=False; wb.Date1904=False
            wb.Worksheets.side_effect=lambda name:pages[name]
            excel=MagicMock(); excel.Workbooks.Open.return_value=wb
            target=Path(folder)/'copy.xlsx'; target.write_bytes(b'original-synthetic')
            wb.SaveAs.side_effect=lambda path,**kw:Path(path).write_bytes(b'updated-synthetic')
            client=MagicMock(); client.DispatchEx.return_value=excel
            win32com=SimpleNamespace(client=client)
            with patch.dict('sys.modules', {'pythoncom':MagicMock(),'win32com':win32com,'win32com.client':client}), \
                 patch.object(excel_secure,'os',SimpleNamespace(name='nt',close=os.close,replace=os.replace)), \
                 patch.object(excel_secure,'is_plain_xlsx',return_value=True), \
                 patch.object(excel_secure,'_com_rows',side_effect=lambda ws:before.get(ws.Name,[])):
                excel_secure.write_com_sheets(target,after)
                self.assertIsNone(pages['일별시세'].cell(3,3).Value2)
                # After conflict resolution, the saved catalog still maps LC to
                # the same physical column beside the untouched user formula.
                before['일별시세'][-1]=(DAY,'=1+1',None)
                store(folder,[price(view_key='two')])
                recovered=sheets(folder)
                excel_secure.write_com_sheets(target,{k:recovered[k] for k in after})
                self.assertEqual(pages['일별시세'].cell(3,3).Value2,15)
                # A formula in the managed cell must block a later withdrawal.
                pages['일별시세'].cell(3,3).HasFormula=True
                before['일별시세'][-1]=(DAY,'=1+1',15)
                store(folder,[price(mid='99',view_key='two')])
                conflicted=sheets(folder)
                saves=wb.SaveAs.call_count
                with self.assertRaisesRegex(excel_secure.SecureExcelError,'사용자 수식'):
                    excel_secure.write_com_sheets(target,{k:conflicted[k] for k in after})
                self.assertEqual(wb.SaveAs.call_count,saves)
            self.assertEqual(pages['일별시세'].cell(3,2).Value2,'=1+1')
            self.assertEqual(pages['일별시세'].cell(1,3).Value2,'LC')
            self.assertEqual(target.read_bytes(),b'updated-synthetic')


class GUIRecoveryTests(unittest.TestCase):
    def pump(self, result, kind='collect'):
        tree = ast.parse((Path(__file__).parent/'gui_v37.py').read_text())
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main_gui')
        pump = next(n for n in main.body if isinstance(n, ast.FunctionDef) and n.name == 'pump')
        q = Queue(); q.put(('done', '수집', kind, result))
        ns = dict(q=q, Empty=Empty, busy=[True], running_buttons=[], cancel_button=MagicMock(),
                  status=MagicMock(), details=MagicMock(), syslog=MagicMock(),
                  messagebox=MagicMock(), root=MagicMock(), pending={}, preview_text=MagicMock(),
                  note=MagicMock(),previewtab=object(),launch=MagicMock(),apply_ecm=MagicMock())
        exec(compile(ast.Module(body=[pump], type_ignores=[]), 'gui_v37.pump', 'exec'), ns)
        ns['pump']()
        return ns

    def test_failed_pipeline_with_no_fx_keeps_gui_pump_running(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(core, 'exclusive_browser_job', side_effect=core.SessionError('busy')):
                result = pipeline_v37.run_collection({'data_dir': folder}, MagicMock(), threading.Event(), lambda x: None)
        ns = self.pump(result)
        ns['root'].after.assert_called_once()
        self.assertIn('실패', ns['status'].set.call_args.args[0])
        self.assertFalse(ns['busy'][0])

    def test_partial_is_not_labeled_complete(self):
        ns = self.pump({'prices': 1, 'diag': {'status': 'partial', 'fx': {}, 'warnings': ['missing']}})
        self.assertIn('부분 완료', ns['status'].set.call_args.args[0])
        ns['root'].after.assert_called_once()

    def test_malformed_event_does_not_stop_next_poll(self):
        ns = self.pump({'prices': 1})
        ns['root'].after.assert_called_once()
        self.assertIn('오류', ns['status'].set.call_args.args[0])
        ns['q'].put(('log','next event'))
        ns['log_widget']=MagicMock()
        ns['pump']()
        ns['log_widget'].insert.assert_called_once_with('end','next event\n')
        self.assertEqual(ns['root'].after.call_count,2)

    def test_clear_only_ecm_preview_displays_and_requests_approval(self):
        result={'workbook_name':'test.xlsx','workbook_path':'C:/ECM/test.xlsx','sheet':'일별요약',
                'stats':{'fill':0,'correction':0,'cleared':1,'unchanged':0,'new_columns':0,
                         'new_dates':0,'missing_source':0},
                'edits':[{'date':DAY,'header':'LC','previous':15,'incoming':None,'decision':'quarantine'}]}
        ns=self.pump(result,'ecm_preview')
        ns['messagebox'].askyesno.assert_called_once()
        self.assertIn('기존 값 비우기 1건',ns['messagebox'].askyesno.call_args.args[1])
        text=''.join(call.args[1] for call in ns['preview_text'].insert.call_args_list)
        self.assertIn('보류(값 비움)',text)
        self.assertEqual(ns['launch'].call_args.args[2],'ecm_apply')


if __name__ == '__main__':
    unittest.main()
