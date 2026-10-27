import copy
import tempfile
import unittest
from unittest.mock import patch


class PublicRecoveryTests(unittest.TestCase):
    def test_actual_pipeline_stage_keeps_failure_reason_for_gui(self):
        import pipeline_v37 as pipeline
        from desktop_tables import collection_issues
        with tempfile.TemporaryDirectory() as t,patch('fdr_provider.collect_and_save',return_value=dict(status='failed',warnings=['proxy rejected public source'])):
            result=pipeline.run_collection(dict(data_dir=t,fmb_enabled=False,fx_enabled=False,naver_enabled=False,fdr_enabled=True),None,lambda:False,lambda _:None)
        self.assertIn('proxy rejected',collection_issues(result['diag']))

    def test_all_public_fetches_failed_is_failed_not_partial_success(self):
        from pathlib import Path
        from fdr_provider import collect_and_save
        def unavailable(*args):raise ConnectionError('synthetic proxy unavailable')
        with tempfile.TemporaryDirectory() as t:
            result=collect_and_save(Path(t)/'test.db',lambda:False,lambda _:None,fetcher=unavailable)
            self.assertEqual(result['status'],'failed')
            self.assertEqual(result['saved'],0)

    def test_public_action_overrides_sources_only_for_this_run(self):
        from desktop_controller import CollectorService
        with tempfile.TemporaryDirectory() as t:
            cfg=dict(data_dir=t,fmb_enabled=True,fx_enabled=True,naver_enabled=True,fdr_enabled=False)
            service=CollectorService(cfg);before=copy.deepcopy(service.settings)
            with patch('pipeline_v37.run_collection',return_value=dict(diag=dict(status='partial',warnings=[],stages={}))) as collect:
                result=service.run('collect_public')
            self.assertEqual(result['status'],'partial')
            run=collect.call_args.args[0]
            self.assertTrue(run['naver_enabled'])
            self.assertFalse(any(run[k] for k in ('fmb_enabled','fx_enabled','fdr_enabled')))
            self.assertEqual(service.settings,before);service.close()

    def test_stage_failures_are_identified_not_generic_connection_advice(self):
        from desktop_tables import collection_issues
        result=collection_issues({'stages':{'fmb':{'status':'failed','error':'9444 connection refused'},'fdr':{'status':'partial','missing':['GOLD'],'warnings':['KR10Y unsupported']}}})
        self.assertIn('금속',result);self.assertIn('9444',result)
        self.assertIn('GOLD',result);self.assertIn('KR10Y',result)

    def test_worker_protocol_uses_utf8_even_on_legacy_locales(self):
        import fdr_provider as f
        import subprocess,sys
        launch=subprocess.Popen;seen=[]
        def child(*args,**kwargs):
            seen.append(kwargs)
            return launch([sys.executable,'-X','utf8','-c','print("{\\"error\\":\\"종가 이력 없음\\"}")'],**kwargs)
        with patch.object(f.subprocess,'Popen',side_effect=child):
            with self.assertRaisesRegex(RuntimeError,'종가 이력 없음'):
                f.fetch_history(f.instruments([])['KOSPI'],'2026-10-01','2026-10-22',lambda:False,3)
        self.assertEqual(seen[0].get('encoding'),'utf-8')


if __name__=='__main__':unittest.main()
