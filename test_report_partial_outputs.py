"""Each report format fails independently; no browser/COM calls in tests."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class PartialReportOutputTests(unittest.TestCase):
    def context(self, folder):
        from test_v37_reports import ReportTests
        from report_model import build_context
        ReportTests().fixture(folder)
        return build_context(folder,captured_at='2026-10-27T08:30:00+09:00')

    def test_excel_failure_keeps_real_html_pptx_json_paths(self):
        import report_exports
        with tempfile.TemporaryDirectory() as folder:
            context=self.context(folder)
            with patch.object(report_exports,'export_excel',side_effect=RuntimeError('fixture COM blocked')):
                result=report_exports.export_reports(context,Path(folder)/'reports',include_excel=True)
            self.assertEqual(set(result),{'html','pptx','context','errors'})
            self.assertIn('fixture COM blocked',result['errors']['excel'])
            for key in ('html','pptx','context'):self.assertTrue(Path(result[key]).is_file())

    def test_html_failure_does_not_prevent_later_formats(self):
        import report_exports
        with tempfile.TemporaryDirectory() as folder:
            context=self.context(folder)
            with patch.object(report_exports,'export_html',side_effect=RuntimeError('fixture HTML failed')):
                result=report_exports.export_reports(context,Path(folder)/'reports',include_excel=True)
            self.assertEqual(set(result),{'pptx','context','excel','errors'})
            for key in ('pptx','context','excel'):self.assertTrue(Path(result[key]).is_file())

    def test_json_failure_does_not_discard_other_formats(self):
        import report_exports
        with tempfile.TemporaryDirectory() as folder:
            context=self.context(folder)
            with patch.object(report_exports,'canonical_json',side_effect=ValueError('fixture JSON failed')):
                result=report_exports.export_reports(context,Path(folder)/'reports')
            self.assertEqual(set(result),{'html','pptx','errors'})
            self.assertIn('context',result['errors'])

    def test_pptx_failure_keeps_html_and_json(self):
        import report_exports
        with tempfile.TemporaryDirectory() as folder:
            context=self.context(folder)
            with patch.object(report_exports,'export_pptx',side_effect=RuntimeError('fixture PPTX failed')):
                result=report_exports.export_reports(context,Path(folder)/'reports')
            self.assertEqual(set(result),{'html','context','errors'})
            self.assertIn('pptx',result['errors'])
            for key in ('html','context'):self.assertTrue(Path(result[key]).is_file())

    def test_all_format_failures_raise_summary(self):
        import report_exports
        with tempfile.TemporaryDirectory() as folder:
            context=self.context(folder)
            with patch.object(report_exports,'export_html',side_effect=RuntimeError('html fixture')), \
                 patch.object(report_exports,'export_pptx',side_effect=RuntimeError('pptx fixture')), \
                 patch.object(report_exports,'canonical_json',side_effect=ValueError('json fixture')):
                with self.assertRaisesRegex(RuntimeError,'html.*pptx.*context'):
                    report_exports.export_reports(context,Path(folder)/'reports')

    def test_success_keeps_existing_paths_only_contract(self):
        import report_exports
        with tempfile.TemporaryDirectory() as folder:
            result=report_exports.export_reports(self.context(folder),Path(folder)/'reports')
            self.assertEqual(set(result),{'html','pptx','context'})

    def test_pipeline_moves_errors_to_warnings_and_preserves_gui_paths(self):
        import pipeline_v37
        from desktop_tables import existing_output_paths
        with tempfile.TemporaryDirectory() as folder:
            context=self.context(folder)
            with patch.object(pipeline_v37.core,'exclusive_browser_job'), \
                 patch.object(pipeline_v37.report_model,'build_context',return_value=context), \
                 patch.object(pipeline_v37.report_exports,'export_excel',side_effect=RuntimeError('fixture COM blocked')):
                result=pipeline_v37.export_only({'data_dir':folder,'reports_only':True})
            self.assertEqual(result['status'],'partial')
            self.assertEqual(set(result['reports']),{'html','pptx','context'})
            self.assertTrue(any('excel' in warning and 'fixture COM blocked' in warning for warning in result['warnings']))
            self.assertEqual(len(existing_output_paths(result)),3)


if __name__=='__main__':unittest.main()
