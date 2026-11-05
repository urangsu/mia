import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from test_report_presentation import sample_context


class BriefingExportTests(unittest.TestCase):
    def test_html_omits_unconfigured_summary_and_escapes_configured_summary(self):
        from report_exports import export_html
        link = dict(title='Lithium report',date='2026-10-21',url='https://pubs.usgs.gov/publication/test')
        with TemporaryDirectory() as folder:
            path = Path(folder)/'report.html'
            export_html(sample_context(),path,briefing={'summary':(), 'links':(link,)})
            html = path.read_text(encoding='utf-8')
            self.assertIn('id="research-links"', html)
            self.assertNotIn('id="daily-briefing"', html)
            export_html(sample_context(),path,briefing={'summary':('<script>not executable</script>',),'links':()})
            html = path.read_text(encoding='utf-8')
        self.assertIn('&lt;script&gt;not executable&lt;/script&gt;',html)
        self.assertLess(html.index('id="daily-briefing"'),html.index('id="metals"'))

    def test_optional_briefing_failure_does_not_stop_numeric_exports(self):
        from pipeline_v37 import export_only
        with TemporaryDirectory() as folder, patch('report_model.build_context', return_value=sample_context()), \
                patch('market_briefing.collect_briefing', side_effect=RuntimeError('private error')):
            result = export_only({'data_dir':folder,'reports_only':True,'public_briefing':True},_lock_held=True)
        self.assertEqual(result['briefing']['status'],'unavailable')
        self.assertIn('html',result['reports'])
        self.assertNotIn('private error',str(result))

    def test_cli_allows_briefing_only_in_explicit_report_mode(self):
        from FastmarketsCollector_v3_7 import main
        with self.assertRaises(SystemExit) as error:
            main(['--once','--public-briefing'])
        self.assertEqual(error.exception.code,2)
