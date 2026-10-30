import unittest
from pathlib import Path

class CarouselTests(unittest.TestCase):
    def test_first_four_positions_are_representatives_not_all_nickel_variants(self):
        from report_presentation import order_metal_rows
        rows=[[{'text':name}] for name in ('니켈 A','니켈 B','코발트','탄산리튬','망간','Payable')]
        self.assertEqual([r[0]['text'] for r in order_metal_rows(rows)][:4],['니켈 A','코발트','탄산리튬','망간'])
    def test_metal_priority_keeps_payables_after_primary_metals(self):
        from report_presentation import metal_priority
        names=['NCM Ni Payable','망간','전지급 탄산리튬','코발트','니켈','구리']
        self.assertEqual(sorted(names,key=metal_priority),['니켈','코발트','전지급 탄산리튬','망간','구리','NCM Ni Payable'])

    def test_rates_precede_market_and_stocks_and_carousel_has_history_host(self):
        template=Path(__file__).with_name('report_template.html').read_text()
        self.assertIn('metal-carousel',template)
        self.assertLess(template.index('aria-label="금리"'),template.index("for table in tables if table.kind in ('market','caps')"))
        self.assertIn('history-host',Path(__file__).with_name('report_history.js').read_text())
