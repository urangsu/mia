from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch,MagicMock


class LMEIntegrationTests(unittest.TestCase):
    def test_storage_snapshot_chart_report_and_operating_columns_share_source(self):
        import FastmarketsCollector_v3_4 as core
        import lme_official as lme
        import report_model as m
        from metal_dashboard import dashboard_data
        from test_lme_official import fixture
        with tempfile.TemporaryDirectory() as temp:
            db=core.path_bundle(Path(temp))['db']
            rows=lme.parse(fixture(),'2026-10-27T08:30:00+09:00')['rows']
            lme.save_rows(db,rows)
            context=m.build_context(temp,captured_at='2026-10-27T08:30:00+09:00')
            self.assertEqual(len(context._sheets['LME_공식원본']),13)
            self.assertEqual(len(dashboard_data(context)['series']),12)
            self.assertEqual(len(context.tables['보고용_LME']),7)
            accumulated=m.make_accumulation_sheets(context)
            catalog=accumulated['가격열설정']
            self.assertEqual(len([r for r in catalog[1:] if r[0].startswith('LME|')]),6)
            self.assertTrue(all('ASK' in r[0] for r in catalog[1:]))
            self.assertEqual(len(accumulated['일별시세'][0]),7)
            self.assertEqual(set(accumulated['일별시세'][1][1:]),{'LME'})
            self.assertEqual(accumulated['일별시세'][2][0],'2026-10-26')
            self.assertNotIn('NAVER|',str(catalog))
            self.assertEqual(context.source_dates['LME'],('2026-10-26',))

    def test_lme_only_collection_stage_does_not_scrape_fastmarkets(self):
        import pipeline_v37 as p
        import lme_official
        from app_settings import validate
        with tempfile.TemporaryDirectory() as temp:
            settings=dict(data_dir=temp,fmb_enabled=False,fx_enabled=False,naver_enabled=False,fdr_enabled=False,lme_enabled=True)
            validate(settings,'collect')
            browser=MagicMock();driver=object();browser.driver=driver
            with patch.object(lme_official,'collect_and_save',return_value=dict(status='complete',rows=12,warnings=[])) as collect,patch.object(p,'export_only',return_value=dict(status='complete',warnings=[],reports={})),patch.object(p.core,'export_files'):
                result=p.run_collection(settings,browser,lambda:False,lambda s:None)
            collect.assert_called_once()
            self.assertIs(collect.call_args.args[0],driver)
            browser.scrape.assert_not_called()
            self.assertEqual(result['diag']['stages']['lme']['status'],'complete')

    def test_ecm_uses_operating_not_market_report_columns(self):
        import report_model as m
        import ecm_excel_sync as ecm
        from test_v37_reports import ReportTests
        with tempfile.TemporaryDirectory() as temp:
            ReportTests().fixture(temp)
            rows,catalog=ecm._snapshot_from_db(temp)
            self.assertNotIn('NAVER|',str(catalog))
            self.assertNotIn('FDR|',str(catalog))
        self.assertEqual(ecm.series_source('LME|LME_NI_CASH_ASK|USD/t|Official|ASK'),'LME')


if __name__=='__main__':unittest.main()
