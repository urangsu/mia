import tempfile
import unittest
from pathlib import Path


class ReportOnlyMarketTests(unittest.TestCase):
    def test_cumulative_metal_workbook_excludes_market_but_report_keeps_it(self):
        import report_model as m
        from test_v37_reports import ReportTests
        with tempfile.TemporaryDirectory() as temp:
            ReportTests().fixture(temp)
            context=m.build_context(temp,end='2026-10-19')
            sheets=m.make_accumulation_sheets(context)
            self.assertNotIn('보고용_시장지표',sheets)
            self.assertNotIn('보고용_주가',sheets)
            self.assertNotIn('NAVER_시총원본',sheets)
            self.assertNotIn('NAVER|',str(sheets['가격열설정']))
            self.assertIn('보고용_시장지표',m.make_workbook_sheets(context))
            self.assertEqual(sheets['RawData'],m.make_workbook_sheets(context)['RawData'])


if __name__=='__main__':unittest.main()
