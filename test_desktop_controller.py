import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('desktop_controller'), '실행 컨트롤러가 필요합니다')
        import desktop_controller as module
        self.m = module
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        import FastmarketsCollector_v3_4 as core
        self.cfg = dict(core.config_load(), data_dir=self.tmp.name,
                        ecm_title='', ecm_search='', workspace_url='not-a-dashboard')
        self.service = module.CollectorService(self.cfg)

    def test_report_failure_is_not_complete_and_does_not_require_ecm_or_login(self):
        with patch('pipeline_v37.export_only', return_value={'status':'failed','warnings':['synthetic export failure'],'reports':{}}):
            result=self.service.run('reports', self.cfg)
        self.assertEqual(result['status'],'failed')
        self.assertIn('synthetic export failure',result['message'])

    def test_snapshot_does_not_save_settings_or_create_db(self):
        self.cfg['workspace_url']=self.m.core.WORKSPACE_URL
        context=SimpleNamespace(tables={},as_of='',snapshot_id='x',warnings=('자료 없음',))
        with patch('report_model.build_context', return_value=context), patch.object(self.m.core,'config_save') as save:
            result=self.service.run('snapshot',self.cfg)
        self.assertEqual(result['data']['snapshot_id'],'x')
        save.assert_not_called()
        self.assertFalse((Path(self.tmp.name)/'fastmarkets_prices_v3.sqlite3').exists())

    def test_snapshot_is_bound_to_service_workspace_not_global_config(self):
        self.cfg['workspace_url']='https://dashboard.fastmarkets.com/w/abcdefghijklmnop/'
        context=SimpleNamespace(tables={},as_of='',snapshot_id='x',warnings=())
        with patch('report_model.build_context',return_value=context) as build:
            result=self.service.run('snapshot',self.cfg)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(build.call_args.kwargs['workspace_id'],'abcdefghijklmnop')

    def test_login_uses_one_time_inputs_not_stored_account(self):
        self.cfg['workspace_url']=self.m.core.WORKSPACE_URL
        browser=MagicMock(); browser.open_workspace.return_value=True
        self.service.browser=browser
        with patch.object(self.m.core,'credentials_get', return_value=('stored','stored-secret')) as stored:
            result=self.service.run('connect',self.cfg,username='once',password='one-time-secret')
        self.assertEqual(result['status'],'complete')
        browser.open_workspace.assert_called_once_with('once','one-time-secret')
        stored.assert_not_called()
        self.assertNotIn('password',self.service.settings)

    def test_login_false_requires_action(self):
        self.cfg['workspace_url']=self.m.core.WORKSPACE_URL
        self.service.browser=MagicMock();self.service.browser.open_workspace.return_value=False
        result=self.service.run('connect',self.cfg,username='once',password='secret')
        self.assertEqual(result['status'],'needs_action')

    def test_busy_does_not_start_second_operation(self):
        self.service._lock.acquire()
        try:result=self.service.run('history',self.cfg)
        finally:self.service._lock.release()
        self.assertEqual(result['status'],'needs_action')

    def test_ecm_apply_without_issued_preview_is_rejected(self):
        self.cfg.update(ecm_title='synthetic.xlsx',ecm_search='synthetic')
        with patch('ecm_excel_sync.apply_ecm_plan') as apply:
            result=self.service.run('ecm_apply',self.cfg,plan={'arbitrary':True})
        self.assertEqual(result['status'],'failed');apply.assert_not_called()

    def test_exception_does_not_expose_password_and_next_run_works(self):
        self.cfg['workspace_url']=self.m.core.WORKSPACE_URL
        self.service.browser=MagicMock()
        self.service.browser.open_workspace.side_effect=RuntimeError('synthetic secret abc-password')
        logs=[];self.service.logger=logs.append
        result=self.service.run('connect',self.cfg,username='once',password='abc-password')
        self.assertEqual(result['status'],'failed')
        self.assertNotIn('abc-password',result['message']+' '.join(logs))
        result=self.service.run('history',self.cfg)
        self.assertEqual(result['status'],'complete')

    def test_report_filters_do_not_modify_saved_settings(self):
        with patch('pipeline_v37.export_only',return_value={'status':'complete','reports':{'html':'synthetic.html'},'warnings':[]}) as export:
            result=self.service.run('reports',self.cfg,start='2026-10-01',end='2026-10-19',series='KOSPI')
        self.assertEqual(result['status'],'complete')
        self.assertTrue(export.call_args.args[0]['reports_only'])
        self.assertEqual(export.call_args.args[0]['report_series'],['KOSPI'])
        self.assertNotIn('reports_only',self.service.settings)

    def test_history_retains_persisted_stage_recovery_reason(self):
        import storage_runtime as store
        path=Path(self.tmp.name)/'fastmarkets_prices_v3.sqlite3'
        run=store.start_run(path,{})
        store.save_stage(path,run,'export','failed',0.1,{'error':'synthetic locked','warnings':['close test workbook']})
        store.finish_run(path,run,'partial')
        result=self.service.run('history',self.cfg)
        stage=result['data']['runs'][0]['stages'][0]
        self.assertEqual(stage.get('error'),'synthetic locked')
        self.assertEqual(stage.get('warnings'),['close test workbook'])

if __name__=='__main__':unittest.main()
