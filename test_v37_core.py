"""v3.7 offline regression contracts; all prices and workbooks are synthetic."""
import unittest
import tempfile
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch,MagicMock
from dataclasses import replace
import FastmarketsCollector_v3_4 as core
import smbs_rates as fx
import ecm_excel_sync as ecm

def quote(**changes):
    p=core.Price('MB-BMS-0012','2026-10-16','10','15','20',None,'$/tonne','Black Mass','BM','Actual','AG Grid','one')
    return replace(p,**changes)

class Core37Tests(unittest.TestCase):
    def test_workspace_identity_is_frozen_per_worker(self):
        with patch.object(core,'config_load',return_value={'workspace_url':core.WORKSPACE_URL}):
            expected=core.current_workspace()
            with core.workspace_scope():
                with patch.object(core,'config_load',return_value={'workspace_url':'invalid'}):
                    self.assertEqual(core.current_workspace(),expected)
            with patch.object(core,'config_load',return_value={'workspace_url':'invalid'}):
                with self.assertRaises(ValueError):core.current_workspace()

    def test_export_cache_invalidated_by_file_or_data_change(self):
        from export_cache import unchanged,record
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'data.xlsx';p.write_bytes(b'protected-by-company-synthetic')
            sheets={'日':[('date','value'),('2026-10-19',1)]}
            self.assertFalse(unchanged(p,sheets));record(p,sheets)
            self.assertTrue(unchanged(p,sheets))
            self.assertFalse(unchanged(p,{'日':[('date','value'),('2026-10-19',2)]}))
            p.write_bytes(b'user-edited');self.assertFalse(unchanged(p,sheets))
    def test_bounded_conflict_must_not_select_one(self):
        issues=[]
        result=fx.prepare_excel_series([quote(),quote(low=None,high=None,mid='99',view_key='two')],[],issues=issues)
        self.assertNotIn('FMB|MB-BMS-0012|$/tonne|Actual|MID',result.get('2026-10-16',{}))
        self.assertTrue(any('충돌' in i for i in issues))

    def test_listener_cache_uses_cdp_identity_and_expires(self):
        s=core.ChromeSession()
        owner={'pid':1,'name':'chrome.exe','local_address':'127.0.0.1',
               'command_line':f'chrome.exe --remote-debugging-port=9444 "--user-data-dir={core.CHROME_PROFILE}"'}
        info={'Browser':'Chrome/155.0','webSocketDebuggerUrl':'ws://127.0.0.1:9444/devtools/browser/one'}
        with patch.object(core,'inspect_windows_listeners',return_value=[owner]) as inspect,patch.object(core,'cdp_version',return_value=info):
            s._validate_listener();s._validate_listener(allow_cache=True)
            self.assertEqual(inspect.call_count,1)
            s._listener_checked_at-=100
            s._validate_listener(allow_cache=True);self.assertEqual(inspect.call_count,2)

    def test_changed_cdp_forces_listener_verification(self):
        s=core.ChromeSession()
        owner={'pid':1,'name':'chrome.exe','local_address':'127.0.0.1',
               'command_line':f'chrome.exe --remote-debugging-port=9444 "--user-data-dir={core.CHROME_PROFILE}"'}
        with patch.object(core,'inspect_windows_listeners',return_value=[owner]) as inspect,patch.object(core,'cdp_version') as info:
            info.return_value={'Browser':'Chrome/155','webSocketDebuggerUrl':'ws://localhost/one'}
            s._validate_listener()
            info.return_value={'Browser':'Chrome/155','webSocketDebuggerUrl':'ws://localhost/two'}
            s._validate_listener(allow_cache=True)
            self.assertEqual(inspect.call_count,2)

    def test_schema_migration_backup_keeps_legacy(self):
        from storage_runtime import migrate_database
        with tempfile.TemporaryDirectory() as t:
            db=Path(t)/'test.sqlite3'
            with closing(sqlite3.connect(db)) as c:
                c.execute('CREATE TABLE legacy(value TEXT)');c.execute("INSERT INTO legacy VALUES('keep')");c.commit()
            r=migrate_database(db)
            self.assertTrue(Path(r['backup']).is_file())
            self.assertFalse(migrate_database(db)['changed'])
            with closing(sqlite3.connect(db)) as c:self.assertEqual(c.execute('SELECT value FROM legacy').fetchone()[0],'keep')

    def test_batch_edits_do_not_span_user_formula_gap(self):
        from com_updates import contiguous_blocks
        edits=[{'row':3,'col':2,'incoming':1},{'row':3,'col':4,'incoming':2},
               {'row':4,'col':2,'incoming':3},{'row':4,'col':4,'incoming':4}]
        blocks=contiguous_blocks(edits)
        self.assertEqual(len(blocks),2)
        self.assertEqual({(b['row'],b['col'],b['height'],b['width']) for b in blocks},{(3,2,2,1),(3,4,2,1)})

    def test_unchanged_ecm_does_not_save(self):
        from contextlib import contextmanager
        k='FMB|MB-LI-0029|$/kg|Actual|MID'
        rows=[('고시일','LC'),('','FMB'),('2026-10-16',15)]
        cat=[('key','name','desc'),(k,'LC','Lithium')]
        wb=MagicMock();wb.Name='test.xlsx';wb.FullName='C:/ECM/test.xlsx';wb.Date1904=False
        ws=wb.Worksheets.return_value;ws.ProtectContents=False
        @contextmanager
        def attach(*a,**kw):yield wb
        with patch.object(ecm,'_attached_excel',attach),patch.object(ecm,'_snapshot_from_db',return_value=(rows,cat,[])), \
             patch.object(ecm,'_read_matrix',return_value=rows),patch.object(ecm,'_read_catalog',return_value=cat):
            plan=ecm.prepare_ecm_plan(Path('.'),'test.xlsx')
            result=ecm.apply_ecm_plan(Path('.'),'test.xlsx',plan)
        wb.Save.assert_not_called()
        self.assertEqual(result['status'],'UNCHANGED')

if __name__=='__main__':unittest.main()
