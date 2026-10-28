"""Synthetic SMM homepage rows. Never commit subscription/live price fixtures."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

CAPTURE='2026-10-28T08:30:00+09:00'


def fixture(day='10/27/2026',nickel='2,232',unit='USD/tonne'):
    rows=[]
    for code,part,key,value in [('SMM-Li-LC-001','lithium','201102250059','10000'),
        ('SMM-NI-NC-001','nickel','201908270001',nickel),('SMM-CO-CM-001','cobalt','201102250375','20000')]:
        rows.append(f'<tr data-row-key="{key}"><td></td><td><a href="/ko/{part}/{key}">Synthetic {code}</a></td><td><span>{value}</span><span>{unit}</span></td><td>-1.2</td><td></td><td>{day}</td></tr>')
    return '<table><thead><tr><th>즐겨찾기</th><th>이름</th><th>평균</th><th>변경</th><th>트렌드</th><th>날짜</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table>'


class SmmPublicTests(unittest.TestCase):
    def test_exact_three_products_date_unit_and_22_32_percent_conversion(self):
        from smm_public import parse,nickel_equivalent
        result=parse(fixture(),captured_at=CAPTURE)
        self.assertEqual(len(result['rows']),3)
        self.assertEqual({r['market_date'] for r in result['rows']},{'2026-10-27'})
        self.assertEqual({r['unit'] for r in result['rows']},{'USD/t'})
        self.assertEqual(nickel_equivalent('2232'),'10000')
        self.assertNotEqual(nickel_equivalent('2232'),'498.1824')

    def test_no_login_or_wrong_unit_or_future_date_is_promoted(self):
        from smm_public import parse
        for html in ('<p>로그인하여 보기</p>',fixture(unit='CNY/tonne'),fixture(day='11/01/2026')):
            self.assertFalse(parse(html,captured_at=CAPTURE)['rows'])
        self.assertFalse(parse(fixture(),captured_at=CAPTURE,source_url='https://evil.test/')['rows'])

    def test_product_href_mismatch_and_unitless_row_rejected(self):
        from smm_public import parse
        bad=fixture().replace('/ko/nickel/201908270001','/ko/lithium/201102250059')
        self.assertEqual(len(parse(bad,captured_at=CAPTURE)['rows']),2)
        self.assertEqual(len(parse(fixture().replace('USD/tonne',''),captured_at=CAPTURE)['rows']),0)

    def test_identical_timestamp_source_conflict_is_quarantined(self):
        from smm_public import parse
        result=parse(fixture()+fixture(nickel='9999'),captured_at=CAPTURE)
        nickel=next(r for r in result['rows'] if r['code']=='SMM-NI-NC-001')
        self.assertIsNone(nickel['value'])
        self.assertEqual(nickel['status'],'conflict')

    def test_storage_idempotency_revision_and_context_propagation(self):
        from smm_public import parse,save_rows
        import FastmarketsCollector_v3_4 as core,report_model
        from metal_dashboard import dashboard_data
        with tempfile.TemporaryDirectory() as folder:
            db=core.path_bundle(Path(folder))['db'];db.parent.mkdir(parents=True,exist_ok=True)
            rows=parse(fixture(),captured_at=CAPTURE)['rows']
            self.assertEqual(save_rows(db,rows)['inserted'],3)
            self.assertEqual(save_rows(db,rows)['unchanged'],3)
            newer=parse(fixture(nickel='4464'),captured_at=CAPTURE)['rows']
            self.assertEqual(save_rows(db,newer)['revised'],1)
            context=report_model.build_context(folder,captured_at=CAPTURE)
            series=[s for s in dashboard_data(context)['series'] if s['source']=='SMM']
            self.assertEqual(len(series),4)
            equivalent=next(s for s in series if s['code'].endswith('_NI_EQ_2232'))
            self.assertEqual(equivalent['points'][0]['value'],20000)
            self.assertEqual(equivalent['unit'],'USD/t Ni')
            self.assertIn('SMM',context.source_dates)
            self.assertIn('SMM|',str(report_model.make_accumulation_sheets(context)['가격열설정']))
            self.assertIn('SMM_시세원본',context._sheets)

    def test_pipeline_stage_defaults_and_explicit_disable(self):
        from app_settings import load,validate
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(load(Path(folder)/'new.json',{})['smm_enabled'])
        self.assertFalse(validate({'data_dir':'synthetic','smm_enabled':False},'history')['smm_enabled'])

    def test_malformed_number_separator_rejected(self):
        from smm_public import parse
        result=parse(fixture(nickel='2,23'),captured_at=CAPTURE)
        self.assertFalse(any(r['code']=='SMM-NI-NC-001' for r in result['rows']))

    def test_korean_name_adjacent_to_code_without_whitespace(self):
        from smm_public import parse
        result=parse(fixture().replace('Synthetic ','한국어품목명'),captured_at=CAPTURE)
        self.assertEqual(len(result['rows']),3)

    def test_storage_rejects_duplicate_conflicting_batch(self):
        from smm_public import parse,save_rows
        with tempfile.TemporaryDirectory() as folder:
            rows=parse(fixture(),captured_at=CAPTURE)['rows']+parse(fixture(nickel='999'),captured_at=CAPTURE)['rows']
            with self.assertRaises(ValueError):save_rows(Path(folder)/'db.sqlite3',rows)

    def test_smm_only_pipeline_is_independent_and_disable_does_not_connect(self):
        from unittest.mock import patch,MagicMock
        import pipeline_v37 as pipeline,smm_public
        with tempfile.TemporaryDirectory() as folder:
            cfg=dict(data_dir=folder,fmb_enabled=False,fx_enabled=False,naver_enabled=False,fdr_enabled=False,lme_enabled=False,smm_enabled=True)
            browser=MagicMock();browser.driver=object()
            with patch.object(smm_public,'collect_and_save',return_value=dict(status='complete',rows=3,warnings=[])) as collect,patch.object(pipeline,'export_only',return_value=dict(status='complete',warnings=[],reports={})):
                result=pipeline.run_collection(cfg,browser,lambda:False,lambda _:None)
                self.assertEqual(result['diag']['stages']['smm']['status'],'complete')
                collect.assert_called_once();browser.scrape.assert_not_called()
                cfg['smm_enabled']=False
                pipeline.run_collection(cfg,browser,lambda:False,lambda _:None)
                self.assertEqual(collect.call_count,1)

    def test_owned_tab_close_failure_still_restores_original(self):
        import smm_public
        from test_lme_official import Driver
        class CloseFails(Driver):
            def close(self):raise RuntimeError('synthetic close failure')
        with tempfile.TemporaryDirectory() as folder:
            driver=CloseFails(fixture())
            result=smm_public.collect_and_save(driver,Path(folder)/'db.sqlite3')
            self.assertEqual(result['status'],'failed')
            self.assertEqual(driver.current_window_handle,'original')

    def test_ecm_source_label_is_smm_not_fastmarkets(self):
        from ecm_excel_sync import series_source
        self.assertEqual(series_source('SMM|SMM-Li-LC-001|USD/t|Actual|AVG'),'SMM')

    def test_monthly_conflict_has_explicit_clear_marker_and_csv_preserves_raw(self):
        import smm_public,report_model,FastmarketsCollector_v3_4 as core
        with tempfile.TemporaryDirectory() as folder:
            db=core.path_bundle(Path(folder))['db'];db.parent.mkdir(parents=True,exist_ok=True)
            smm_public.save_rows(db,smm_public.parse(fixture()+fixture(nickel='999'),captured_at=CAPTURE)['rows'])
            context=report_model.build_context(folder,captured_at=CAPTURE)
            keys=[r for r in context._sheets['보류셀'] if r[0]=='월별시세' and 'SMM-NI-NC-001' in r[2]]
            self.assertEqual(len(keys),2)
            target=Path(folder)/'smm.csv';smm_public.export_csv(db,target)
            self.assertIn('SMM-NI-NC-001',target.read_text(encoding='utf-8-sig'))



if __name__=='__main__':unittest.main()
