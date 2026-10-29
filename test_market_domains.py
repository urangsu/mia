import sqlite3
from contextlib import closing
import unittest
from types import SimpleNamespace

class DomainTests(unittest.TestCase):
    def test_sparse_schema_and_three_views(self):
        from market_domains import initialize
        with closing(sqlite3.connect(':memory:')) as cx:
            initialize(cx)
            for domain in ('market','metal','stock'):
                self.assertEqual(cx.execute('SELECT count(*) FROM domain_'+domain).fetchone()[0],0)
            self.assertEqual(cx.execute('SELECT count(*) FROM prior_estimates').fetchone()[0],0)

    def test_inversion_and_invalid_inputs(self):
        from market_domains import estimate_prior
        self.assertEqual(estimate_prior('110','10',kind='pct'),'100')
        self.assertEqual(estimate_prior('4.096','8.1',kind='bp'),'4.015')
        for value,change in [('100','-100'),('NaN','2'),('100','NaN')]:
            with self.assertRaises(ValueError):estimate_prior(value,change,kind='pct')

    def test_estimates_are_separate_and_require_confirmed_dates(self):
        from market_domains import initialize,save_estimate
        with closing(sqlite3.connect(':memory:')) as cx:
            initialize(cx)
            args=dict(domain='market',code='KOSPI',current_date='2026-10-29',prior_date='2026-10-28',
                value='110',change='10',kind='pct',unit='pt',source='https://example.org',basis_confirmed=True)
            save_estimate(cx,**args);save_estimate(cx,**args)
            self.assertEqual(cx.execute('SELECT value,status FROM prior_estimates').fetchone(),('100','derived_estimated'))
            self.assertEqual(cx.execute('SELECT count(*) FROM prior_estimates').fetchone()[0],1)
            with self.assertRaises(ValueError):save_estimate(cx,**dict(args,basis_confirmed=False))
            with self.assertRaises(ValueError):save_estimate(cx,**dict(args,prior_date='2026-10-29'))

    def test_four_yield_cards_use_three_decimal_levels_and_bp_changes(self):
        from market_domains import rate_cards
        context=SimpleNamespace(tables={'보고용_시장지표':[
            ('지표','수치','전일대비','단위'),('US10Y','4.096','0.081','%')]})
        cards=rate_cards(context)
        self.assertEqual(len(cards),4)
        self.assertEqual(cards[0]['value'],'4.096%');self.assertEqual(cards[0]['change'],'+8.1bp')
        self.assertEqual(cards[2]['value'],'—');self.assertIn('AA−',cards[3]['label'])
