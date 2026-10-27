"""Offline orchestration contracts, not live browser/Windows acceptance."""
import importlib.util
import tempfile
import threading
import unittest
from contextlib import contextmanager,closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

HERE=Path(__file__).parent


class PipelineTests(unittest.TestCase):
    def module(self):
        target=HERE/'pipeline_v37.py'
        self.assertTrue(target.exists(),'pipeline not implemented')
        spec=importlib.util.spec_from_file_location('pipeline_v37',target)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def test_fmb_failure_does_not_lose_fx_naver_or_export(self):
        m=self.module()
        events=[]
        @contextmanager
        def lock():
            events.append('lock');yield;events.append('unlock')
        with tempfile.TemporaryDirectory() as folder:
            settings={'data_dir':folder,'lookback_days':31,'naver_enabled':True,'password':'secret'}
            browser=SimpleNamespace(driver=object(),scrape=MagicMock(side_effect=RuntimeError('fmb offline')))
            with patch.object(m.core,'exclusive_browser_job',lock),patch.object(m.core,'fx_one_time',return_value={'collected':4,'warnings':[]}) as fx,patch.object(m.naver_markets,'collect_and_save',return_value={'status':'complete','indicators':8,'equities':11,'warnings':[]}) as naver,patch.object(m,'export_only',return_value={'workbook':'out.xlsx','reports':{},'warnings':[],'snapshot_id':'abc','status':'complete'}) as export,patch.object(m.storage_runtime,'incremental_days',return_value=7):
                result=m.run_collection(settings,browser,threading.Event(),lambda s:None)
            self.assertEqual(result['prices'],0)
            self.assertTrue(result['diag']['fmb_failed'])
            self.assertEqual(result['diag']['fx']['collected'],4)
            self.assertEqual(result['diag']['naver']['indicators'],8)
            self.assertEqual(result['diag']['status'],'partial')
            self.assertEqual(events,['lock','unlock'])
            self.assertTrue(fx.call_args.kwargs['defer_export'])
            self.assertIs(fx.call_args.kwargs['driver'],browser.driver)
            self.assertEqual(naver.call_count,1)
            self.assertEqual(export.call_count,1)
            import sqlite3,json
            with closing(sqlite3.connect(Path(folder)/'fastmarkets_prices_v3.sqlite3')) as cx:
                saved=json.loads(cx.execute('SELECT settings_json FROM v37_runs').fetchone()[0])
                self.assertNotIn('password',saved)
                self.assertEqual(cx.execute('SELECT status FROM v37_runs').fetchone()[0],'partial')

    def test_cancellation_stops_following_sources(self):
        m=self.module();cancel=threading.Event()
        with tempfile.TemporaryDirectory() as folder:
            def scrape(*a,**kw):cancel.set();return [1],{'warnings':[]}
            browser=SimpleNamespace(driver=object(),scrape=MagicMock(side_effect=scrape))
            with patch.object(m.core,'exclusive_browser_job'),patch.object(m.core,'fx_one_time') as fx,patch.object(m.naver_markets,'collect_and_save') as naver,patch.object(m,'export_only') as export:
                result=m.run_collection({'data_dir':folder,'lookback_days':31},browser,cancel,lambda s:None)
            self.assertTrue(result['cancelled']);fx.assert_not_called();naver.assert_not_called();export.assert_not_called()

    def test_one_immutable_context_for_all_outputs(self):
        m=self.module();context=SimpleNamespace(snapshot_id='abc',warnings=())
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'new.xlsx'
            with patch.object(m.report_model,'build_context',return_value=context) as build,patch.object(m.report_model,'make_workbook_sheets',return_value={'sheet':[(1,)]}) as sheets,patch.object(m.report_exports,'export_excel',return_value=str(target)) as excel,patch.object(m.report_exports,'export_reports',return_value={'html':'out.html','pptx':'out.pptx','context':'out.json'}) as reports,patch.object(m,'IS_WINDOWS',False):
                result=m.export_only({'data_dir':folder,'workbook_path':str(target)})
            self.assertEqual(build.call_count,1)
            self.assertIs(excel.call_args.args[0],context)
            self.assertIs(reports.call_args.args[0],context)
            self.assertTrue(reports.call_args.kwargs['include_excel'])
            self.assertEqual(result['snapshot_id'],'abc')

    def test_nonwindows_existing_workbook_is_preserved_and_reports_continue(self):
        m=self.module();context=SimpleNamespace(snapshot_id='abc',warnings=())
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'existing.xlsx';target.touch()
            with patch.object(m.report_model,'build_context',return_value=context),patch.object(m.report_model,'make_workbook_sheets',return_value={}),patch.object(m.report_exports,'export_excel') as excel,patch.object(m.report_exports,'export_reports',return_value={'html':'ok'}) as reports,patch.object(m,'IS_WINDOWS',False):
                result=m.export_only({'data_dir':folder,'workbook_path':str(target)})
            excel.assert_not_called();self.assertEqual(reports.call_count,1)
            self.assertEqual(result['status'],'partial');self.assertTrue(result['warnings'])
            self.assertIsNone(result['workbook'])

    def test_windows_uses_preserving_com_sheets(self):
        m=self.module();context=SimpleNamespace(snapshot_id='abc',warnings=())
        with tempfile.TemporaryDirectory() as folder:
            sheets={'sheet':[(1,)]}
            with patch.object(m.report_model,'build_context',return_value=context),patch.object(m.report_model,'make_accumulation_sheets',return_value=sheets),patch.object(m.excel_secure,'write_com_sheets',return_value='com.xlsx') as write,patch.object(m.report_exports,'export_excel') as ordinary,patch.object(m.report_exports,'export_reports',return_value={}),patch.object(m,'IS_WINDOWS',True):
                m.export_only({'data_dir':folder})
            self.assertIs(write.call_args.args[1],sheets)
            ordinary.assert_not_called()

    def test_failed_context_build_never_emits_mixed_reports(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(m.report_model,'build_context',side_effect=RuntimeError('invalid snapshot')),patch.object(m.report_exports,'export_reports') as reports:
                result=m.export_only({'data_dir':folder})
            self.assertEqual(result['status'],'failed');self.assertTrue(result['warnings'])
            reports.assert_not_called()

    def test_incremental_days_and_deferred_output_contract(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as folder:
            browser=SimpleNamespace(driver=object(),scrape=MagicMock(return_value=([1],{'warnings':[]})))
            with patch.object(m.core,'exclusive_browser_job'),patch.object(m.core,'export_files'),patch.object(m.core,'fx_one_time',return_value={'collected':4}),patch.object(m.naver_markets,'collect_and_save',return_value={'status':'complete'}),patch.object(m.storage_runtime,'incremental_days',return_value=7) as incremental,patch.object(m,'export_only',return_value={'workbook':'a','reports':{},'warnings':[],'snapshot_id':'abc','status':'complete'}):
                result=m.run_collection({'data_dir':folder,'lookback_days':31},browser,lambda:False,lambda s:None)
            self.assertEqual(browser.scrape.call_args.args[0],7)
            self.assertTrue(browser.scrape.call_args.kwargs['defer_export'])
            self.assertEqual(result['diag']['status'],'complete')

    def test_reports_only_never_writes_workbook(self):
        m=self.module();context=SimpleNamespace(snapshot_id='abc',warnings=())
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(m.report_model,'build_context',return_value=context) as build,patch.object(m.report_exports,'export_excel') as excel,patch.object(m.excel_secure,'write_com_sheets') as com,patch.object(m.report_exports,'export_reports',return_value={'html':'h','pptx':'p','context':'j'}):
                result=m.export_only({'data_dir':folder,'reports_only':True,'report_start':'2026-01-01'})
            excel.assert_not_called();com.assert_not_called()
            self.assertEqual(build.call_args.kwargs['start'],'2026-01-01')
            self.assertIsNone(result['workbook'])
            self.assertEqual(result['status'],'complete')

    def test_filtered_normal_export_is_rejected_before_snapshot_or_write(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(m.report_model,'build_context') as build,patch.object(m.report_exports,'export_excel') as excel:
                result=m.export_only({'data_dir':folder,'report_series':['GOLD']})
            self.assertEqual(result['status'],'failed');build.assert_not_called();excel.assert_not_called()

    def test_partial_fmb_blocks_autoecm_and_missing_driver_reconnects(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as folder:
            driver=object()
            browser=SimpleNamespace(driver=None,connect=MagicMock(return_value=driver),scrape=MagicMock(return_value=([],{'warnings':['incomplete inventory']})))
            with patch.object(m.core,'exclusive_browser_job'),patch.object(m.core,'export_files'),patch.object(m.core,'fx_one_time',return_value={'collected':4}) as fx,patch.object(m.naver_markets,'collect_and_save',return_value={'status':'complete'}),patch.object(m,'export_only',return_value={'workbook':'a','reports':{},'warnings':[],'status':'complete'}) as exported:
                result=m.run_collection({'data_dir':folder,'report_start':'2026-01-01','reports_only':True},browser,lambda:False,lambda s:None)
            self.assertTrue(result['diag']['fmb_failed'])
            self.assertIs(fx.call_args.kwargs['driver'],driver)
            self.assertTrue((Path(folder)/'last_diagnostic.json').exists())
            self.assertNotIn('report_start',exported.call_args.args[0])
            self.assertNotIn('reports_only',exported.call_args.args[0])

    def test_naver_can_recover_after_fx_connection_failure(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as folder:
            driver=object()
            browser=SimpleNamespace(driver=None,connect=MagicMock(side_effect=[RuntimeError('transient'),driver]),scrape=MagicMock(side_effect=RuntimeError('fmb offline')))
            with patch.object(m.core,'exclusive_browser_job'),patch.object(m.core,'export_files'),patch.object(m.naver_markets,'collect_and_save',return_value={'status':'complete'}) as naver,patch.object(m,'export_only',return_value={'warnings':[],'status':'complete'}):
                result=m.run_collection({'data_dir':folder},browser,lambda:False,lambda s:None)
            self.assertEqual(result['diag']['naver']['status'],'complete')
            self.assertIs(naver.call_args.args[0],driver)


if __name__=='__main__':unittest.main()
