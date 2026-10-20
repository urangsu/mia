import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pipeline_v37 as pipeline
import FastmarketsCollector_v3_7 as entry


class SourceOptionsTests(unittest.TestCase):
    def test_disabled_fmb_and_fx_are_not_called(self):
        with tempfile.TemporaryDirectory() as t:
            settings=dict(data_dir=t, fmb_enabled=False, fx_enabled=False, naver_enabled=True)
            browser=SimpleNamespace(driver=object(), scrape=MagicMock())
            with patch.object(pipeline.core,'exclusive_browser_job'), patch.object(pipeline.core,'export_files'), \
                 patch.object(pipeline.core,'fx_one_time') as fx, \
                 patch.object(pipeline.naver_markets,'collect_and_save',return_value={'status':'complete','warnings':[]}) as naver, \
                 patch.object(pipeline,'export_only',return_value={'status':'complete','warnings':[],'reports':{'html':'synthetic'},'workbook':'synthetic.xlsx'}):
                result=pipeline.run_collection(settings,browser,lambda:False,lambda msg:None)
            browser.scrape.assert_not_called();fx.assert_not_called();naver.assert_called_once()
            self.assertEqual(result['diag']['fmb']['status'],'disabled')
            self.assertEqual(result['diag']['fx']['status'],'disabled')
            self.assertEqual(result['diag']['status'],'complete')

    def test_naver_only_does_not_require_valid_fastmarkets_workspace(self):
        with tempfile.TemporaryDirectory() as t:
            settings=dict(data_dir=t,fmb_enabled=False,fx_enabled=False,naver_enabled=True,workspace_url='not-a-dashboard')
            browser=SimpleNamespace(driver=object(),scrape=MagicMock())
            with patch.object(pipeline.core,'exclusive_browser_job'),patch.object(pipeline.core,'export_files'), \
                 patch.object(pipeline.naver_markets,'collect_and_save',return_value={'status':'complete','warnings':[]}) as naver, \
                 patch.object(pipeline,'export_only',return_value={'status':'complete','warnings':[],'reports':{}}):
                pipeline.run_collection(settings,browser,lambda:False,lambda msg:None)
            naver.assert_called_once();browser.scrape.assert_not_called()

    def test_cli_blocks_corrupt_settings_before_browser_creation(self):
        with patch.object(entry.core,'config_load',return_value={'_settings_warning':'synthetic corrupt config','data_dir':'synthetic'}), \
             patch.object(entry.core,'ChromeSession') as browser,patch('pipeline_v37.run_collection') as collect:
            self.assertEqual(entry.main(['--once']),2)
        browser.assert_not_called();collect.assert_not_called()

    def test_cli_preserves_saved_naver_disabled_without_explicit_override(self):
        with tempfile.TemporaryDirectory() as t:
            settings=dict(data_dir=t, naver_enabled=False)
            with patch.object(entry.core,'config_load',return_value=settings), \
                 patch('pipeline_v37.export_only',return_value={'status':'complete'}) as export:
                self.assertEqual(entry.main(['--export-only']),0)
            self.assertIs(export.call_args.args[0]['naver_enabled'],False)

if __name__=='__main__':unittest.main()
