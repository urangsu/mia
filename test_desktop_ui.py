"""Real Qt widget contracts; fake only external browser/COM service."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import copy
import threading
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt, QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea


class FakeService:
    def __init__(self):
        self.settings = {'data_dir': '/tmp/mia-test', 'lookback_days': 31}
        self.calls = []
        self.result = None
        self.gate = None
        self.cancelled = False
        self.closed = False

    def run(self, action, settings=None, **payload):
        self.calls.append((action, copy.deepcopy(settings), payload, threading.get_ident()))
        if self.gate:
            self.gate.wait(2)
        if self.result:
            if callable(self.result):
                return self.result(action)
            return self.result
        data = {'tables': {}, 'runs': []}
        if action == 'save_settings':
            self.settings = copy.deepcopy(settings)
            data = {'settings': self.settings}
        if action == 'ecm_preview':
            return {'status': 'needs_action', 'message': '승인 필요', 'data': {'workbook_path': '/approved/a.xlsx', 'workbook_name': 'a.xlsx', 'sheet': 'daily', 'edits': [{'cell': 'B2', 'value': 1}], 'stats': {'conflicts': 1}}, 'warnings': []}
        return {'status': 'complete', 'message': '확인됨', 'data': data, 'warnings': []}

    def cancel(self):
        self.cancelled = True

    def close(self):
        self.closed = True


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from desktop_ui import MainWindow
        self.service = FakeService()
        self.window = MainWindow(self.service)
        self.window.show()
        self.wait_idle()

    def wait_idle(self):
        for _ in range(300):
            QTest.qWait(5)
            if not self.window.busy:
                return
        self.fail('Worker did not finish')

    def tearDown(self):
        if self.service.gate:
            self.service.gate.set()
        self.wait_idle()
        self.window.close()
        for _ in range(200):
            QTest.qWait(5)
            if self.service.closed and not self.window.thread.isRunning():
                break
        self.assertFalse(self.window.thread.isRunning())
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_navigation_and_explicit_settings_save(self):
        self.window.nav.setCurrentRow(4)
        self.assertEqual(self.window.pages.currentIndex(), 4)
        self.window.fields['data_dir'].setText('/tmp/changed')
        self.window.submit('diagnose')
        self.wait_idle()
        self.assertEqual(self.service.settings['data_dir'], '/tmp/mia-test')
        self.window.buttons['save_settings'].click()
        self.wait_idle()
        self.assertEqual(self.service.settings['data_dir'], '/tmp/changed')
        self.assertNotEqual(self.service.calls[-1][3], threading.get_ident())

    def test_public_source_settings_and_stock_close_table_connected(self):
        self.assertIn('fdr_enabled',self.window.fields)
        self.assertIn('보고용_주가',self.window.tables)
        self.window.fields['fdr_enabled'].setChecked(True)
        self.window.fields['fdr_stock_codes'].setText('005490,005930')
        self.window.fields['fdr_timeout'].setValue(12)
        self.window.buttons['save_settings'].click();self.wait_idle()
        self.assertEqual(self.service.settings['fdr_stock_codes'],['005490','005930'])
        self.assertEqual(self.service.settings['fdr_timeout'],12)

    def test_password_is_one_time_and_not_saved(self):
        self.window.username.setText('user')
        self.window.password.setText('secret')
        self.window.buttons['connect'].click()
        self.wait_idle()
        action, settings, payload, _ = self.service.calls[-1]
        self.assertEqual(action, 'connect')
        self.assertEqual(payload['password'], 'secret')
        self.assertNotIn('password', settings)
        self.assertEqual(self.window.password.text(), '')

    def test_failure_is_not_success_and_retry_preserves_action(self):
        self.service.result = {'status': 'failed', 'message': '연결 실패', 'data': {}, 'warnings': []}
        self.window.submit('connect')
        self.wait_idle()
        self.assertIn('실패', self.window.status.text())
        self.assertTrue(self.window.retry.isEnabled())

    def test_missing_history_and_search_are_rendered(self):
        self.window.render_snapshot({'tables': {'보고용_시장지표': [('종목', '이전 종가', '상태'), ('KOSPI', None, 'missing_history')]}, 'as_of': '2026-10-19'})
        table = self.window.tables['보고용_시장지표']
        self.assertEqual(table.model.rows[0][2], 'missing_history')
        self.window.search.setText('not-found')
        self.assertEqual(table.proxy.rowCount(), 0)
        self.assertIn('2026-10-19', self.window.as_of.text())

    def test_ecm_apply_requires_confirmation_and_preserves_plan(self):
        self.window.submit('ecm_preview')
        self.wait_idle()
        self.assertIn('/approved/a.xlsx', self.window.ecm_detail.toPlainText())
        self.assertIn('/approved/a.xlsx', self.window.ecm_target.text())
        self.assertIn('충돌 철회', self.window.ecm_stats.text())
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.No):
            self.window.buttons['ecm_apply'].click()
        self.assertNotEqual(self.service.calls[-1][0], 'ecm_apply')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.window.buttons['ecm_apply'].click()
        self.wait_idle()
        self.assertEqual(self.service.calls[-1][2]['plan']['workbook_path'], '/approved/a.xlsx')

    def test_busy_disables_actions_and_freezes_settings(self):
        self.service.gate = threading.Event()
        self.window.submit('collect')
        self.window.fields['data_dir'].setText('/later')
        QTest.qWait(20)
        self.assertFalse(self.window.buttons['save_settings'].isEnabled())
        self.assertFalse(self.window.buttons['ecm_preview'].isEnabled())
        self.assertNotEqual(self.service.calls[-1][1]['data_dir'], '/later')
        self.service.gate.set()
        self.wait_idle()

    def test_close_cancels_and_waits_for_worker(self):
        self.service.gate = threading.Event()
        self.window.submit('collect')
        QTest.qWait(20)
        self.window.close()
        self.assertTrue(self.service.cancelled)
        self.assertTrue(self.window.thread.isRunning())
        self.service.gate.set()
        self.wait_idle()

    def test_preview_is_invalidated_if_settings_change(self):
        self.window.submit('ecm_preview')
        self.wait_idle()
        self.window.fields['ecm_search'].setText('different-document')
        self.assertIsNone(self.window.pending_plan)
        self.assertFalse(self.window.buttons['ecm_apply'].isEnabled())

    def test_preview_started_with_old_settings_cannot_be_applied(self):
        self.service.gate = threading.Event()
        self.window.submit('ecm_preview')
        self.window.fields['ecm_search'].setText('changed-during-preview')
        self.service.gate.set()
        self.wait_idle()
        self.assertIsNone(self.window.pending_plan)

    def test_reports_forward_filters_without_saving(self):
        self.window.report_start.setText('2026-10-01')
        self.window.report_end.setText('2026-10-19')
        self.window.report_series.setText('KOSPI, MB-LI-0029')
        self.window.buttons['reports'].click()
        self.wait_idle()
        self.assertEqual(self.service.calls[-1][2], {'start': '2026-10-01', 'end': '2026-10-19', 'series': ['KOSPI', 'MB-LI-0029']})
        self.assertNotIn('save_settings', [c[0] for c in self.service.calls])

    def test_partial_history_has_stage_error_details(self):
        self.service.result = {'status': 'complete', 'message': '기록', 'data': {'runs': [{'run_id': 'r1', 'status': 'partial', 'stages': {'excel': {'error': 'locked'}}}]}}
        self.window.buttons['history'].click()
        self.wait_idle()
        self.assertIn('locked', str(self.window.history_table.model.rows))

    def test_arbitrary_preview_result_is_not_an_approval_plan(self):
        self.service.result = {'status': 'needs_action', 'message': '로그인 필요', 'data': {'text': 'MFA'}}
        self.window.submit('ecm_preview')
        self.wait_idle()
        self.assertIsNone(self.window.pending_plan)
        self.assertFalse(self.window.buttons['ecm_apply'].isEnabled())

    def test_summary_uses_actual_dates_counts_and_representative_symbols(self):
        self.window.fields['representative_symbols'].setText('LI')
        self.window.render_snapshot({'tables': {'보고용_금속시세': [('종목','고시일','Mid','단위','구분','출처'), ('LI','2026-10-19',100,'USD','mid','FMB'), ('CO','2026-10-18',200,'USD','mid','FMB')]}})
        self.assertIn('2개', self.window.summary.cards[0].text())
        self.assertIn('2026-10-19', self.window.summary.cards[0].text())
        self.assertIn('LI', self.window.summary.representatives.text())
        self.assertNotIn('CO', self.window.summary.representatives.text())

    def test_empty_onboarding_settings_button_navigates(self):
        table = self.window.tables['보고용_금속시세']
        table.setup_button.click()
        self.assertEqual(self.window.pages.currentIndex(), 4)

    def test_settings_no_horizontal_clipping_at_minimum_width(self):
        self.window.resize(1060, 760)
        self.window.nav.setCurrentRow(4)
        QTest.qWait(20)
        scroll = self.window.findChild(QScrollArea)
        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)

    def test_collect_refreshes_snapshot_and_preserves_outcome_log(self):
        self.window.submit('collect')
        self.wait_idle()
        self.assertEqual([c[0] for c in self.service.calls][-2:], ['collect', 'snapshot'])
        self.assertIn('시세 수집', self.window.log.toPlainText())

    def test_ecm_no_edits_has_no_apply(self):
        self.service.result = {'status': 'needs_action', 'message': '미리보기', 'data': {'workbook_path': '/a.xlsx', 'workbook_name': 'a.xlsx', 'sheet': 'daily', 'stats': {}, 'edits': []}}
        self.window.submit('ecm_preview')
        self.wait_idle()
        self.assertIsNone(self.window.pending_plan)
        self.assertFalse(self.window.buttons['ecm_apply'].isEnabled())
        self.assertIn('변경 없음', self.window.ecm_stats.text())

    def test_ecm_clear_only_is_explicit_applyable_change(self):
        self.service.result = {'status': 'needs_action', 'message': '미리보기', 'data': {'workbook_path': '/a.xlsx', 'workbook_name': 'a.xlsx', 'sheet': 'daily', 'stats': {'cleared': 1}, 'edits': [{'date':'2026-10-19', 'header':'LI', 'previous':10, 'incoming':None, 'decision':'quarantine'}]}}
        self.window.submit('ecm_preview')
        self.wait_idle()
        self.assertTrue(self.window.buttons['ecm_apply'].isEnabled())
        self.assertIn('비움', str(self.window.ecm_table.model.rows))

    def test_nested_output_paths_are_discovered_on_worker(self):
        from pathlib import Path
        seen = []
        original = Path.is_file
        def checked(path):
            seen.append(threading.get_ident())
            return original(path)
        with tempfile.NamedTemporaryFile(suffix='.html') as output:
            self.service.result = {'status':'complete', 'message':'출력됨', 'data': {'diag': {'reports': {'html': output.name}}}}
            with patch.object(Path, 'is_file', checked):
                self.window.submit('reports')
                self.wait_idle()
            self.assertIn(str(Path(output.name).resolve()), self.window.report_paths)
            self.assertNotIn(threading.get_ident(), seen)

    def test_technical_failure_is_bounded_and_raw_detail_only_in_log(self):
        raw = 'Traceback Selenium Message: ' + 'session disconnected at webdriver ' * 15
        self.service.result = {'status': 'failed', 'message': raw, 'data': {'error': raw, 'status': 'failed'}}
        self.window.submit('reports')
        self.wait_idle()
        self.assertLessEqual(len(self.window.status.text()), 180)
        self.assertNotIn('Traceback', self.window.status.text())
        self.assertNotIn('Traceback', self.window.report_detail.toPlainText())
        self.assertNotIn('{', self.window.report_detail.toPlainText())
        self.assertIn(raw, self.window.log.toPlainText())
        self.assertIn('실행 기록', self.window.status.text())

    def test_reports_show_human_file_labels_and_paths_not_result_json(self):
        with tempfile.NamedTemporaryFile(suffix='.html') as output:
            self.service.result = {'status': 'complete', 'message': '보고서를 생성했습니다.', 'data': {'reports': {'html': output.name}, 'diagnostic': {'internal': 'raw technical metadata'}}}
            self.window.submit('reports')
            self.wait_idle()
            detail = self.window.report_detail.toPlainText()
            self.assertIn('HTML 보고서', detail)
            self.assertIn(output.name, detail)
            self.assertNotIn('raw technical metadata', detail)
            self.assertNotIn('{', detail)

    def test_background_refresh_preserves_partial_collect_and_export_outcomes(self):
        for action in ('collect', 'export'):
            with self.subTest(action=action):
                self.service.result = lambda name: {'status': 'partial' if name == action else 'complete', 'message': 'Excel 출력 실패' if name == action else '자료 조회 완료', 'data': {'tables': {}} if name == 'snapshot' else {}, 'warnings': []}
                self.window.submit(action)
                self.wait_idle()
                self.assertIn('부분 완료', self.window.status.text())
                self.assertIn('Excel 출력 실패', self.window.status.text())
                self.assertTrue(self.window.retry.isEnabled())
                self.assertEqual(self.window.last_action, action)
                self.assertEqual([c[0] for c in self.service.calls][-2:], [action, 'snapshot'])

    def test_render_exception_restores_controls_and_offers_read_only_retry(self):
        with patch.object(self.window, 'render_snapshot', side_effect=ValueError('malformed display fixture')):
            self.window.submit('snapshot')
            self.wait_idle()
        self.assertTrue(self.window.buttons['save_settings'].isEnabled())
        self.assertTrue(self.window.buttons['collect'].isEnabled())
        self.assertIn('화면 표시', self.window.status.text())
        self.assertIn('ValueError', self.window.log.toPlainText())
        self.assertEqual(self.window.last_action, 'snapshot')
        self.window.retry.click()
        self.wait_idle()
        self.assertEqual(self.service.calls[-1][0], 'snapshot')

    def test_collect_output_failure_retry_does_not_rescrape(self):
        self.service.result = lambda name: {'status': 'partial' if name == 'collect' else 'complete', 'message':'Excel 출력 실패' if name == 'collect' else '조회 완료', 'data': {'diag': {'stages': {'fmb': {'status':'complete'}, 'export': {'status':'failed'}}}} if name == 'collect' else {'tables': {}}, 'warnings': []}
        self.window.submit('collect')
        self.wait_idle()
        self.window.retry.click()
        self.wait_idle()
        actions = [c[0] for c in self.service.calls]
        self.assertEqual(actions.count('collect'), 1)
        self.assertIn('export', actions)


if __name__ == '__main__':
    unittest.main()
