"""Real exchange_calendars sessions, no network or browser."""
import unittest


class SessionsTests(unittest.TestCase):
    def api(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('market_sessions'), 'market session adapter missing')
        import market_sessions
        return market_sessions

    def test_monday_korean_morning_excludes_weekend_and_today(self):
        self.assertEqual(self.api().expected_pair('XKRX','2026-10-19T08:30:00+09:00'),('2026-10-16','2026-10-15'))

    def test_us_holiday_and_dst_use_actual_close(self):
        m=self.api()
        self.assertEqual(m.expected_pair('XNYS','2026-07-06T08:30:00+09:00'),('2026-07-02','2026-07-01'))
        self.assertEqual(m.expected_pair('XNYS','2026-10-22T08:30:00+09:00'),('2026-10-21','2026-10-20'))
        self.assertEqual(m.expected_pair('XNYS','2026-11-03T08:30:00+09:00'),('2026-11-02','2026-10-30'))

    def test_not_closed_yet_or_publication_grace_excluded(self):
        m=self.api()
        self.assertFalse(m.session_finished('XNYS','2026-10-21','2026-10-22T04:59:00+09:00'))
        self.assertFalse(m.session_finished('XNYS','2026-10-21','2026-10-22T05:05:00+09:00'))
        self.assertTrue(m.session_finished('XNYS','2026-10-21','2026-10-22T08:30:00+09:00'))
        self.assertFalse(m.session_finished('XKRX','2026-10-22','2026-10-22T23:30:00+09:00'))

    def test_early_close_is_honored(self):
        self.assertTrue(self.api().session_finished('XNYS','2026-11-27','2026-11-28T04:00:00+09:00'))

    def test_invalid_or_unsupported_calendars_fail_closed(self):
        m=self.api()
        with self.assertRaises(ValueError):m.expected_pair('KR10Y','2026-10-22T08:30:00+09:00')
        with self.assertRaises(ValueError):m.expected_pair('XNYS','2026-10-22T08:30:00')
        self.assertFalse(m.session_finished('XKRX','2026-10-18','2026-10-22T08:30:00+09:00'))


if __name__=='__main__':unittest.main()
