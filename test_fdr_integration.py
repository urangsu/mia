from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch,MagicMock


class IntegrationTests(unittest.TestCase):
    def test_public_only_pipeline_never_connects_browser_and_records_stage(self):
        import pipeline_v37 as p
        import fdr_provider
        browser=SimpleNamespace(driver=None,connect=MagicMock(side_effect=AssertionError('browser not allowed')),scrape=MagicMock())
        with tempfile.TemporaryDirectory() as t:
            cfg=dict(data_dir=t,fmb_enabled=False,fx_enabled=False,naver_enabled=False,fdr_enabled=True,fdr_stock_codes=['005490'])
            with patch.object(fdr_provider,'collect_and_save',return_value={'status':'partial','warnings':['missing history'],'saved':1}) as collect, \
                 patch.object(p,'export_only',return_value={'status':'complete','reports':{},'warnings':[]}):
                result=p.run_collection(cfg,browser,lambda:False,lambda _:None)
            collect.assert_called_once()
            self.assertEqual(result['diag']['stages']['fdr']['status'],'partial')
            browser.connect.assert_not_called();browser.scrape.assert_not_called()

    def test_config_validates_and_roundtrips_public_source(self):
        from app_settings import validate,save,load
        cfg=dict(data_dir='synthetic',fmb_enabled=False,fx_enabled=False,naver_enabled=False,fdr_enabled=True,fdr_stock_codes=['005490'],fdr_timeout=20)
        self.assertEqual(validate(cfg,'collect')['fdr_stock_codes'],['005490'])
        with self.assertRaises(ValueError):validate(dict(cfg,fdr_stock_codes=['5490']),'save_settings')
        with self.assertRaises(ValueError):validate(dict(cfg,fdr_timeout=0),'save_settings')
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'settings.json';save(path,cfg)
            self.assertTrue(load(path,{})['fdr_enabled'])

    def test_cli_public_only_preserves_workspace_without_browser_access(self):
        import FastmarketsCollector_v3_7 as e
        with tempfile.TemporaryDirectory() as t,patch.object(e.core,'config_load',return_value={'data_dir':'unused'}), \
             patch('pipeline_v37.run_collection',return_value={'diag':{'status':'partial'}}) as collect:
            self.assertEqual(e.main(['--once','--public-only','--data-dir',t]),2)
            cfg=collect.call_args.args[0]
            self.assertTrue(cfg['fdr_enabled'])
            self.assertFalse(any(cfg[k] for k in ('fmb_enabled','fx_enabled','naver_enabled')))

    def test_fdr_off_explicitly_has_no_network_stage(self):
        import pipeline_v37 as p
        import fdr_provider
        with tempfile.TemporaryDirectory() as t,patch.object(fdr_provider,'collect_and_save') as collect, \
             patch.object(p,'export_only',return_value={'status':'complete','reports':{},'warnings':[]}):
            p.run_collection(dict(data_dir=t,fmb_enabled=False,fx_enabled=False,naver_enabled=False,fdr_enabled=False),object(),lambda:False,lambda _:None)
            collect.assert_not_called()

    def test_new_public_only_db_exports_without_fmb_prices_table(self):
        import pipeline_v37 as p,fdr_provider
        from market_sessions import expected_pair,capture_time
        def fetch(spec,*args):
            return [{'date':day,'close':str(100-i)} for i,day in enumerate(expected_pair(spec.calendar,capture_time()))]
        with tempfile.TemporaryDirectory() as t,patch.object(fdr_provider,'fetch_history',side_effect=fetch):
            cfg=dict(data_dir=t,fmb_enabled=False,fx_enabled=False,naver_enabled=False,fdr_enabled=True)
            result=p.run_collection(cfg,None,lambda:False,lambda _:None)
            self.assertEqual(result['diag']['stages']['csv']['status'],'complete')
            text=(Path(t)/'public_closes.csv').read_text(encoding='utf-8-sig')
            self.assertIn('NAVER:005490',text)
            self.assertTrue(result['diag']['reports']['pptx'])


if __name__=='__main__':unittest.main()
