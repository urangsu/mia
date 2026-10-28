"""Synthetic chart contracts, including missing points and source isolation."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import test_metal_dashboard as fixtures


class MetalHistoryTests(unittest.TestCase):
    def test_all_metal_dates_and_sources_share_one_main_table(self):
        from test_report_presentation import sample_context
        from report_presentation import presentation_tables
        tables=presentation_tables(sample_context())
        metals=[t for t in tables if t['kind']=='metals']
        self.assertEqual(len(metals),1)
        self.assertEqual(len(metals[0]['rows']),2)
        self.assertIn('고시일',metals[0]['headers'])
        self.assertIn('2026.10.21',str(metals[0]['rows']))
        self.assertIn('2026.10.27',str(metals[0]['rows']))

    def test_real_stored_series_bind_to_clickable_row_without_filling_gaps(self):
        from report_presentation import presentation_tables
        with tempfile.TemporaryDirectory() as folder:
            context=fixtures.MetalDashboardTests().context(folder)
            table=next(t for t in presentation_tables(context) if t['kind']=='metals')
            lithium=next(row[0] for row in table['rows'] if '탄산리튬' in row[0]['text'])
            history=lithium['history']
            self.assertEqual([p['value'] for p in history['points']],[100,None,101])
            self.assertEqual(history['unit'],'$/kg')
            self.assertIn('view-a',history['id'])

    def test_html_contains_accessible_toggle_and_separate_source_link(self):
        from report_exports import export_html
        with tempfile.TemporaryDirectory() as folder:
            context=fixtures.MetalDashboardTests().context(folder)
            path=Path(folder)/'report.html';export_html(context,path)
            main=path.read_text().split('<details id="source-basis"',1)[0]
            self.assertIn('class="history-toggle"',main)
            self.assertIn('aria-expanded="false"',main)
            self.assertIn('가격 이력',main)
            self.assertIn('data-history=',main)
            self.assertIn('1개월',main)
            self.assertIn('history-chart',main)
            self.assertIn('history-observations',main)


if __name__=='__main__':unittest.main()
