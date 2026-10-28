import unittest
from datetime import date,timedelta
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
import test_desktop_ui as legacy


class MetalsUITests(unittest.TestCase):
    def test_one_metal_surface_and_click_latest_row_selects_history(self):
        panel=self.window.metals
        titles=[self.window.dashboard_tabs.tabText(i) for i in range(self.window.dashboard_tabs.count())]
        self.assertNotIn('금속',titles)
        items=[dict(id=key,code=key,name='품목 '+key,group='리튬',unit='USD/t',mode='Actual',source='SMM',
            source_url='https://www.metal.com/',view_key='public',conditions='Synthetic',
            points=[dict(date='2026-10-27',value=value,status='observed')]) for key,value in [('a',100),('b',200)]]
        panel.set_data(dict(series=items,coverage=[]))
        self.assertEqual(panel.latest.model.rowCount(),2)
        target=panel.latest.proxy.mapFromSource(panel.latest.model.index(1,0))
        panel.latest.view.clicked.emit(target)
        self.assertEqual(panel.chart.series['id'],'b')
        self.assertEqual(panel.chart.points[0]['value'],200)

    def test_smm_prices_are_counted_in_the_metal_summary(self):
        self.window.render_snapshot({'tables':{'보고용_SMM':[
            ('품목명','고시일','Mid','단위','구분','출처','코드'),
            ('전지급 탄산리튬','2026-10-28',100,'USD/t','Actual','https://www.metal.com/','SMM-Li-LC-001')]}})
        self.assertIn('1개',self.window.summary.cards[0].text())
        self.assertIn('탄산리튬',self.window.summary.representatives.text())

    def test_small_window_remains_resizable_with_scrollable_metal_content(self):
        self.window.resize(1060,760);QTest.qWait(10)
        self.assertLessEqual(self.window.height(),760)
        self.assertGreaterEqual(self.window.metals.history.geometry().top(),self.window.metals.chart.geometry().bottom())

    def test_all_history_chart_coordinate_work_is_linear_not_quadratic(self):
        from desktop_metals import MetalChart
        chart=MetalChart()
        points=[dict(date=(date(2020,1,1)+timedelta(days=i)).isoformat(),value=i,status='observed') for i in range(300)]
        with patch('desktop_metals.date',wraps=date) as dates:
            chart.set_series(dict(name='TEST'),points)
            for point in chart.points:chart._x(point['date'])
            self.assertLessEqual(dates.fromisoformat.call_count,600)

    setUp=legacy.DesktopTests.setUp
    tearDown=legacy.DesktopTests.tearDown
    wait_idle=legacy.DesktopTests.wait_idle

    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_metals_first_and_source_details_collapsed_until_explicit_toggle(self):
        self.assertEqual(self.window.dashboard_tabs.tabText(0),'원료·금속 시황')
        self.window.render_snapshot({'metals':{'series':[],'coverage':[dict(source='LME',product='니켈 Cash/3M',status='unsupported',count=0,reason='미지원')]}})
        self.assertIn('unsupported',str(self.window.coverage_table.model.rows))
        self.assertFalse(self.window.sources_toggle.isChecked())
        self.window.nav.setCurrentRow(1)
        self.assertFalse(self.window.report_sources.isVisible())
        self.window.sources_toggle.click()
        self.assertTrue(self.window.report_sources.isVisible())

    def test_period_and_group_filter_change_table_and_chart_together(self):
        panel=self.window.metals
        item=dict(id='a',code='NI',name='황산니켈',group='니켈',unit='USD/t',mode='Actual',
            source='FMB',source_url='fixture://source',view_key='v1',conditions='sulfate · China',
            points=[dict(date='2026-01-01',value=100,status='observed'),dict(date='2026-10-20',value=None,status='missing'),dict(date='2026-10-21',value=101,status='observed')])
        panel.set_data(dict(series=[item],coverage=[]))
        panel.group.setCurrentText('니켈');panel.period.setCurrentText('1개월')
        self.assertEqual(len(panel.chart.points),2)
        self.assertEqual(panel.history.model.rowCount(),2)
        self.assertIn('값 없음',panel.chart.tooltip_for(panel.chart.points[0]))
        self.assertIn('101',panel.chart.tooltip_for(panel.chart.points[-1]))
        self.assertIn('Actual',panel.chart.tooltip_for(panel.chart.points[-1]))
        panel.group.setCurrentText('리튬')
        self.assertEqual(panel.chart.points,[]);self.assertEqual(panel.history.model.rowCount(),0)

    def test_public_button_returns_result_without_changing_saved_sources(self):
        self.assertIn('collect_public',self.window.buttons)
        before=dict(self.service.settings)
        self.window.buttons['collect_public'].click();self.wait_idle()
        self.assertTrue(any(c[0]=='collect_public' for c in self.service.calls))
        self.assertEqual(self.service.settings,before)


if __name__=='__main__':unittest.main()
