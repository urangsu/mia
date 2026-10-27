"""No browser or network: source-session freshness of observed close pairs."""
import copy
import importlib
from pathlib import Path
import unittest
from unittest.mock import patch


CAPTURED = '2026-10-27T08:30:00+09:00'


def pair(identity='KOSPI', previous='2026-10-26', prior='2026-10-23'):
    return dict(instrument_id=identity, previous_date=previous, prior_date=prior,
                previous_close='110', prior_close='100', change='10', pct='10',
                unit='포인트', currency=None, status='close_pair',
                source_url='https://stock.naver.com/synthetic', quarantined_dates=[])


class FreshnessTests(unittest.TestCase):
    def api(self):
        self.assertTrue(Path(__file__).with_name('naver_freshness.py').is_file(), 'freshness helper missing')
        return importlib.import_module('naver_freshness')

    def test_expected_real_sessions_preserve_confirmed_pair(self):
        original = pair()
        checked, warnings = self.api().check_pair(original, CAPTURED)
        self.assertEqual(checked['status'], 'close_pair')
        self.assertEqual(checked['previous_date'], '2026-10-26')
        self.assertEqual(checked['expected_previous_date'], '2026-10-26')
        self.assertEqual(checked['expected_prior_date'], '2026-10-23')
        self.assertEqual(checked['freshness_calendar'], 'XKRX')
        self.assertEqual(warnings, [])
        self.assertNotIn('freshness_calendar', original)

    def test_older_pair_stays_visible_but_is_not_current_confirmed(self):
        original = pair(previous='2026-10-23', prior='2026-10-22')
        before = copy.deepcopy(original)
        checked, warnings = self.api().check_pair(original, CAPTURED)
        self.assertEqual(checked['status'], 'stale_history')
        for field in ('previous_close', 'prior_close', 'previous_date', 'prior_date', 'unit', 'currency'):
            self.assertEqual(checked[field], before[field])
        self.assertTrue(warnings)
        self.assertEqual(original, before)
        checked['quarantined_dates'].append('not-on-original')
        self.assertEqual(original['quarantined_dates'], [])

    def test_us_holiday_expected_pair_not_calendar_day_subtraction(self):
        checked, warnings = self.api().check_pair(pair('SP500', '2026-07-02', '2026-07-01'),
                                                 '2026-07-06T08:30:00+09:00')
        self.assertEqual(checked['status'], 'close_pair')
        self.assertEqual(checked['freshness_calendar'], 'XNYS')
        self.assertEqual(warnings, [])

    def test_calendar_mapping_is_source_specific_and_preserves_contract_identity(self):
        module = self.api()
        for identity, calendar in [('KOSDAQ', 'XKRX'), ('SP500', 'XNYS'), ('NASDAQ', 'XNAS'),
                                   ('GOLD', 'CMES'), ('WTI', 'CMES')]:
            original = pair(identity)
            original.update(price_type='recent_contract_futures', unit='USD/bbl', currency='USD')
            with self.subTest(identity=identity), patch.object(module, 'expected_pair', return_value=('2026-10-26', '2026-10-23')) as expected:
                checked, warnings = module.check_pair(original, CAPTURED)
                expected.assert_called_once_with(calendar, CAPTURED)
                self.assertEqual(checked['price_type'], 'recent_contract_futures')
                self.assertEqual(checked['unit'], 'USD/bbl')
                self.assertEqual(checked['currency'], 'USD')
                self.assertEqual(warnings, [])
        equity = pair()
        del equity['instrument_id']
        equity['stock_code'] = '005930'
        checked, warnings = module.check_pair(equity, CAPTURED)
        self.assertEqual(checked['freshness_calendar'], 'XKRX')
        self.assertEqual(warnings, [])

    def test_calendar_exception_never_confirms_old_history(self):
        module = self.api()
        original = pair()
        with patch.object(module, 'expected_pair', side_effect=RuntimeError('calendar unavailable')):
            checked, warnings = module.check_pair(original, CAPTURED)
        self.assertEqual(checked['status'], 'calendar_unverified')
        self.assertEqual(checked['previous_close'], '110')
        self.assertTrue(warnings)

    def test_bonds_keep_actual_dates_but_never_borrow_stock_holidays(self):
        module = self.api()
        for identity in ('US10Y', 'KR10Y'):
            with self.subTest(identity=identity), patch.object(module, 'expected_pair') as expected:
                checked, warnings = module.check_pair(pair(identity), CAPTURED)
                expected.assert_not_called()
                self.assertEqual(checked['status'], 'calendar_unverified')
                self.assertEqual(checked['previous_date'], '2026-10-26')
                self.assertTrue(warnings)

    def test_missing_pair_status_is_unchanged(self):
        original = pair()
        original.update(status='missing_history', prior_close=None, prior_date=None)
        checked, warnings = self.api().check_pair(original, CAPTURED)
        self.assertEqual(checked, original)
        self.assertIsNot(checked, original)
        self.assertEqual(warnings, [])


if __name__ == '__main__':
    unittest.main()
