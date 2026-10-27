"""Offscreen Qt presentation contracts; fake external service only."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from test_desktop_ui import FakeService


class CompactDesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from desktop_ui import MainWindow
        self.service=FakeService();self.window=MainWindow(self.service)
        self.window.show();self.wait_idle()

    def wait_idle(self):
        for _ in range(300):
            QTest.qWait(5)
            if not self.window.busy:return
        self.fail('worker did not become idle')

    def tearDown(self):
        self.wait_idle();self.window.close()
        for _ in range(200):
            QTest.qWait(5)
            if not self.window.thread.isRunning():break
        self.assertFalse(self.window.thread.isRunning())
        self.window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete)

    def failure(self):
        return dict(status='failed',message='fixture failed',warnings=['long detailed failure'],
            data={'diag':{'warnings':['long detailed failure'],'stages':{'naver':{'status':'failed','warnings':['DOM fixture unavailable']}}}})

    def test_warning_details_collapsed_and_failure_does_not_auto_open(self):
        w=self.window
        w.render_snapshot({'tables':{},'warnings':['missing_history fixture']})
        w._present_result('collect',self.failure(),False)
        self.assertFalse(w.snapshot_warning.isVisible())
        self.assertFalse(w.collection_errors.isVisible())
        self.assertIn('실패',w.state_chip.text())
        w.details_toggle.click();QTest.qWait(1)
        self.assertTrue(w.snapshot_warning.isVisible())
        self.assertTrue(w.collection_errors.isVisible())
        self.assertEqual(w.nav.currentRow(),0)
        w.details_toggle.click()
        w.render_snapshot({'tables':{},'warnings':['new warning']})
        w._present_result('collect',self.failure(),False)
        self.assertFalse(w.snapshot_warning.isVisible())
        self.assertFalse(w.collection_errors.isVisible())

    def test_market_tables_are_report_only(self):
        w=self.window
        titles={w.dashboard_tabs.tabText(i) for i in range(w.dashboard_tabs.count())}
        self.assertEqual(titles,{'원료·금속 시황','금속','환율','원천 수집 범위'})
        self.assertIn('보고용_주가',w.tables)
        self.assertNotEqual(w.dashboard_tabs.indexOf(w.tables['보고용_주가']),0)
        self.assertEqual(w.dashboard_tabs.indexOf(w.tables['보고용_주가']),-1)
        self.assertGreaterEqual(w.report_tabs.indexOf(w.tables['보고용_주가']),0)
        self.assertTrue(w.summary.cards[2].isHidden())
        w.nav.setCurrentRow(1)
        self.assertTrue(w.report_tabs.isVisible())

    def test_lme_has_explicit_setting_and_report_table(self):
        w=self.window
        self.assertIn('lme_enabled',w.fields)
        self.assertIn('보고용_LME',w.tables)
        self.assertGreaterEqual(w.report_tabs.indexOf(w.tables['보고용_LME']),0)

    def test_market_collection_action_is_on_report_page_and_snapshot_id_is_not_heading(self):
        w=self.window
        self.assertFalse(w.buttons['collect_public'].isVisible())
        w.render_snapshot({'tables':{},'as_of':'2026-10-27T08:30:00+09:00','snapshot_id':'abcdef1234567890'})
        self.assertNotIn('abcdef',w.as_of.text())
        self.assertIn('abcdef',w.as_of.toolTip())
        w.nav.setCurrentRow(1)
        self.assertTrue(w.buttons['collect_public'].isVisible())

    def test_lme_prices_reach_metal_summary_without_a_configured_fmb_symbol(self):
        w=self.window
        rows=[('금속','고시일','계약','방향','가격','단위','기준','출처'),
              ('니켈','2026-10-26','Cash','Ask',100.25,'USD/t','Official Settlement','source')]
        w.render_snapshot({'tables':{'보고용_LME':rows},'warnings':[]})
        self.assertIn('1개',w.summary.cards[0].text())
        self.assertIn('니켈',w.summary.representatives.text())
        self.assertIn('100.25',w.summary.representatives.text())

    def test_metal_source_column_hidden_after_refresh_but_searchable(self):
        w=self.window
        data={'tables':{'보고용_금속시세':[('품목명','고시일','Mid','단위','구분','출처'),
            ('fixture','2026-10-26',100,'USD','Actual','hidden-provenance')]}}
        for _ in range(2):w.render_snapshot(data)
        table=w.tables['보고용_금속시세']
        self.assertTrue(table.view.isColumnHidden(5))
        self.assertEqual(table.model.rows[0][5],'hidden-provenance')
        table.search('hidden-provenance');self.assertEqual(table.proxy.rowCount(),1)
        table.search('not-found');self.assertEqual(table.proxy.rowCount(),0)

    def test_metal_history_source_hidden_but_retained(self):
        panel=self.window.metals
        item=dict(id='fixture',group=panel.group.currentText(),name='fixture',unit='USD',mode='Actual',
            source='FMB',source_url='fixture://source',conditions='fixture',code='fixture',view_key='fixture',
            points=[dict(date='2026-10-26',value=100,status='observed')])
        panel.set_data({'series':[item]});panel.refresh()
        self.assertTrue(panel.history.view.isColumnHidden(5))
        self.assertEqual(panel.history.model.rows[0][5],'FMB')


if __name__=='__main__':unittest.main()
