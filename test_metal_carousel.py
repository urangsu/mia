import unittest
from pathlib import Path

class CarouselTests(unittest.TestCase):
    def test_first_four_positions_are_representatives_not_all_nickel_variants(self):
        from report_presentation import order_metal_rows
        rows=[[{'text':name}] for name in ('니켈 A','니켈 B','코발트','탄산리튬','망간','Payable')]
        self.assertEqual([r[0]['text'] for r in order_metal_rows(rows)][:4],['니켈 A','코발트','탄산리튬','Payable'])
    def test_requested_two_row_order(self):
        from report_presentation import order_metal_rows
        rows=[[{'text':name}] for name in ('구리','망간','블랙매스','탄산리튬','니켈','코발트')]
        self.assertEqual([r[0]['text'] for r in order_metal_rows(rows)],['니켈','코발트','탄산리튬','블랙매스','망간','구리'])
    def test_circular_metal_marks_and_white_cards(self):
        from report_presentation import html_tables
        from test_report_presentation import sample_context
        metals=next(t for t in html_tables(sample_context()) if t['kind']=='metals')
        self.assertEqual(metals['rows'][0][0].get('metal_mark'),'LC')
        template=Path(__file__).with_name('report_template.html').read_text()
        self.assertIn('class="metal-mark"',template)
        css=Path(__file__).with_name('report_dashboard.css').read_text()
        self.assertIn('background:var(--base);border-color:var(--line)',css)
    def test_metal_priority_keeps_payables_after_primary_metals(self):
        from report_presentation import metal_priority
        names=['NCM Ni Payable','망간','전지급 탄산리튬','코발트','니켈','구리']
        self.assertEqual(sorted(names,key=metal_priority),['니켈','코발트','전지급 탄산리튬','망간','구리','NCM Ni Payable'])

    def test_rates_precede_market_and_stocks_and_metals_use_a_responsive_grid(self):
        template=Path(__file__).with_name('report_template.html').read_text()
        self.assertLess(template.index('aria-label="금리"'),template.index("for table in tables if table.kind in ('market','caps')"))
        self.assertIn('id="metal-grid"',template)
        self.assertNotIn('data-rail-step',template)
        css=Path(__file__).with_name('report_dashboard.css').read_text()
        self.assertIn('repeat(var(--metal-columns),minmax(0,1fr))',css)
