"""Synthetic fixtures: never real subscribed prices or company DOM."""
import tempfile
import unittest
from pathlib import Path


class MetalDashboardTests(unittest.TestCase):
    def test_empty_view_never_inherits_another_views_value_or_source(self):
        import FastmarketsCollector_v3_4 as core,report_model
        from metal_dashboard import dashboard_data
        with tempfile.TemporaryDirectory() as t:
            self.context(t)
            empty=core.Price('MB-LI-TEST','2026-10-21',None,None,None,None,'$/kg',
                'Lithium carbonate, battery grade, cif China','fixture','Actual','fixture://empty-view','view-empty','')
            core.save_sqlite(core.path_bundle(Path(t))['db'],[empty],[],dict(widget_count=1,found_symbols=['MB-LI-TEST'],warnings=[]))
            series=dashboard_data(report_model.build_context(t,end='2026-10-22'))['series']
            row=next(s for s in series if s['view_key']=='view-empty')
            self.assertIsNone(row['points'][0]['value'])
            self.assertEqual(row['source_url'],'fixture://empty-view')

    def test_unknown_is_explicit_not_an_invented_lme_name(self):
        from series_mapping import product_info
        info=product_info('MB-NI-9999','', '$/tonne','Actual')
        self.assertEqual(info['name'],'품목명 확인 필요')
        self.assertEqual(info['group'],'미분류')
        self.assertNotIn('LME',info['conditions'])

    def test_product_identity_keeps_original_conditions(self):
        from series_mapping import product_info
        a=product_info('MB-LI-TEST','Lithium carbonate, battery grade, cif China, Japan & Korea','$/kg','Actual')
        self.assertIn('탄산리튬',a['name']);self.assertIn('전지급',a['name'])
        self.assertIn('cif China',a['conditions']);self.assertEqual(a['group'],'리튬')
        b=product_info('MB-BM-TEST','Black mass, NCM payable indicator, nickel, cif South Korea','%','Forecast')
        self.assertEqual(b['group'],'블랙매스');self.assertIn('Payable',b['name'])
        self.assertIn('Forecast',b['conditions'])

    def context(self,t):
        import FastmarketsCollector_v3_4 as core
        import report_model
        rows=[]
        for day,mid in [('2026-10-19',100),('2026-10-20',None),('2026-10-21',101)]:
            rows.append(core.Price('MB-LI-TEST',day,mid,mid,mid,None,'$/kg',
                'Lithium carbonate, battery grade, cif China, Japan & Korea','fixture','Actual','fixture://FMB','view-a',''))
        rows.append(core.Price('MB-NI-TEST','2026-10-21',10,10,10,None,'$/tonne',
            'Nickel sulfate, China','fixture','Actual','fixture://FMB','view-b',''))
        core.save_sqlite(core.path_bundle(Path(t))['db'],rows,[],dict(widget_count=2,found_symbols=['MB-LI-TEST','MB-NI-TEST'],warnings=[]))
        return report_model.build_context(t,end='2026-10-22',synthetic=True)

    def test_same_snapshot_series_preserves_gaps_unit_and_view(self):
        from metal_dashboard import dashboard_data
        with tempfile.TemporaryDirectory() as t:
            c=self.context(t);result=dashboard_data(c)
            lithium=next(s for s in result['series'] if s['code']=='MB-LI-TEST')
            self.assertEqual(lithium['group'],'리튬');self.assertEqual(lithium['view_key'],'view-a')
            self.assertEqual([p['value'] for p in lithium['points']],[100,None,101])
            self.assertEqual(lithium['unit'],'$/kg')
            self.assertEqual(result['snapshot_id'],c.snapshot_id)
            self.assertTrue(any(r['source']=='LME' and r['status']=='unsupported' for r in result['coverage']))

    def test_report_displays_product_before_code_without_changing_daily_keys(self):
        with tempfile.TemporaryDirectory() as t:
            c=self.context(t);rows=c.tables['보고용_금속시세'];h=rows[0]
            row=next(r for r in rows[1:] if r[h.index('코드')]=='MB-LI-TEST')
            self.assertIn('탄산리튬',row[0]);self.assertEqual(row[2],101)
            self.assertIn('FMB|MB-LI-TEST|$/kg|Actual|MID',str(c._sheets['가격열설정']))

    def test_period_uses_calendar_months_and_keeps_null(self):
        from metal_dashboard import filter_points
        points=[dict(date=d,value=v) for d,v in [('2026-01-30',1),('2026-01-31',None),('2026-02-28',2)]]
        self.assertEqual([p['value'] for p in filter_points(points,months=1,end='2026-02-28')],[1,None,2])
        self.assertEqual(filter_points(points,start='2026-01',end='2026-01')[-1]['value'],None)


if __name__=='__main__':unittest.main()
