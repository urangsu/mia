"""Synthetic public-table contracts, no company browser or actual LME prices."""
import importlib
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


CAPTURED = '2026-10-27T10:00:00+09:00'


def fixture(valid='26 Oct 2026', unit='USD per metric tonne'):
    headers = '<thead><tr><th></th><th colspan="2">Cash</th><th colspan="2">3-month</th><th colspan="2">15-month</th></tr><tr><th></th>' + '<th>Bid</th><th>Ask</th>'*3 + '</tr></thead>'
    rows = ''.join('<tr><th scope="row">'+metal+'</th>'+''.join(
        '<td data-table-column-header="'+side+'">'+value+'</td>' for side, value in
        [('Bid', '100.25'), ('Ask', '110.25'), ('Bid', '120.25'), ('Ask', '130.25'), ('Bid', '140.25'), ('Ask', '150.25')])+'</tr>'
        for metal in ('Copper', 'Nickel', 'Cobalt'))
    return '<div id="dataset-tab-0"><div class="data-set-tabs__content-top"><span>Prices shown in '+unit+'</span><span>Data valid for '+valid+'</span><span class="data-set-tabs__refreshed-on">27 Oct 2026</span></div><table>'+headers+'<tbody>'+rows+'</tbody></table></div>'


class Driver:
    def __init__(self, html, redirect=None):
        self.current_window_handle = 'original'
        self.window_handles = ['original']
        self.page_source = html
        self.current_url = 'https://original.example/'
        self.redirect = redirect
        self.switch_to = self
    def new_window(self, kind):
        self.window_handles.append('owned')
        self.current_window_handle = 'owned'
    def window(self, handle):
        self.current_window_handle = handle
    def get(self, url):
        self.current_url = self.redirect or url
    def close(self):
        self.window_handles.remove(self.current_window_handle)


class LmeTests(unittest.TestCase):
    def api(self):
        self.assertTrue(Path(__file__).with_name('lme_official.py').is_file(), 'LME public table module missing')
        return importlib.import_module('lme_official')

    def test_scoped_valid_date_not_refresh_date_and_explicit_sides(self):
        parsed = self.api().parse('<p>Data valid for 1 Jan 2030</p>'+fixture(), CAPTURED)
        self.assertEqual(len(parsed['rows']), 12)
        self.assertEqual(parsed['warnings'], [])
        for row in parsed['rows']:
            self.assertEqual(row['market_date'], '2026-10-26')
            self.assertEqual((row['unit'], row['currency'], row['price_type']), ('USD/t', 'USD', 'Official'))
            self.assertIn(row['contract'], ('Cash', '3-month'))
            self.assertIn(row['side'], ('Bid', 'Ask'))
            self.assertEqual(row['is_settlement'], row['contract']=='Cash' and row['side']=='Ask')
            self.assertNotIn('mid', row)
        nickel = next(row for row in parsed['rows'] if row['instrument_id']=='LME_NI_CASH_ASK')
        self.assertEqual(nickel['value'], '110.25')
        self.assertEqual(json.loads(nickel['raw_json'])['source_date_label'], 'Data valid for 26 Oct 2026')

    def test_missing_or_future_source_date_wrong_unit_and_wrong_origin_fail_closed(self):
        m = self.api()
        for html in (fixture(valid='28 Oct 2026'), fixture(valid='26 Oktober 2026'),
                     fixture().replace('Data valid for 26 Oct 2026', ''),
                     fixture(unit='USD per pound'), fixture().replace('dataset-tab-0', 'other-dataset')):
            with self.subTest(html=html[:100]):
                result = m.parse(html, CAPTURED)
                self.assertEqual(result['rows'], [])
                self.assertTrue(result['warnings'])
        result = m.parse(fixture(), CAPTURED, source_url='https://evil.example/lme')
        self.assertEqual(result['rows'], [])

    def test_bid_above_ask_quarantines_pair_and_dash_is_not_zero(self):
        m = self.api()
        bad = fixture().replace('>100.25</td>', '>999.25</td>', 1)
        parsed = m.parse(bad, CAPTURED)
        self.assertEqual(len(parsed['rows']), 10)
        self.assertTrue(any('Bid' in warning for warning in parsed['warnings']))
        missing = m.parse(fixture().replace('>100.25</td>', '>-</td>', 1), CAPTURED)
        self.assertEqual(len(missing['rows']), 11)
        self.assertFalse(any(row['value']=='0' for row in missing['rows']))

    def test_column_header_mismatch_cannot_shift_contracts(self):
        html = fixture().replace('data-table-column-header="Bid"', 'data-table-column-header="Ask"', 1)
        parsed = self.api().parse(html, CAPTURED)
        self.assertFalse(any(r['instrument_id']=='LME_CU_CASH_BID' for r in parsed['rows']))
        self.assertTrue(parsed['warnings'])

    def test_own_storage_idempotence_and_value_revision_audit(self):
        m = self.api()
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp)/'own.db'
            self.assertEqual(m.load_rows(db), [])
            self.assertFalse(db.exists())
            rows = m.parse(fixture(), CAPTURED)['rows']
            self.assertEqual(m.save_rows(db, rows)['inserted'], 12)
            self.assertEqual(m.save_rows(db, rows)['unchanged'], 12)
            rows[1] = dict(rows[1], value='111.25')
            self.assertEqual(m.save_rows(db, rows)['revised'], 1)
            loaded = m.load_rows(db)
            self.assertEqual(len(loaded), 12)
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('SELECT count(*) FROM lme_official_revisions').fetchone()[0], 1)
                old, new = cx.execute('SELECT old_json,new_json FROM lme_official_revisions').fetchone()
                self.assertEqual(json.loads(old)['value'], '110.25')
                self.assertEqual(json.loads(new)['value'], '111.25')

    def test_owned_tab_collection_restores_original_and_rejects_redirect(self):
        m = self.api()
        with tempfile.TemporaryDirectory() as temp:
            driver = Driver(fixture())
            result = m.collect_and_save(driver, Path(temp)/'prices.db', lambda: False, lambda message: None)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['rows'], 12)
            self.assertEqual(driver.window_handles, ['original'])
            self.assertEqual(driver.current_window_handle, 'original')
            redirect = Driver(fixture(), 'https://evil.example/')
            result = m.collect_and_save(redirect, Path(temp)/'blocked.db', lambda: False, lambda message: None)
            self.assertEqual(result['status'], 'failed')
            self.assertFalse((Path(temp)/'blocked.db').exists())
            self.assertEqual(redirect.current_window_handle, 'original')

    def test_cancellation_never_writes_and_closes_only_owned_tab(self):
        m = self.api()
        with tempfile.TemporaryDirectory() as temp:
            driver = Driver(fixture())
            result = m.collect_and_save(driver, Path(temp)/'cancelled.db',
                                        lambda: driver.current_window_handle == 'owned', lambda message: None)
            self.assertEqual(result['status'], 'cancelled')
            self.assertFalse((Path(temp)/'cancelled.db').exists())
            self.assertEqual(driver.window_handles, ['original'])
            self.assertEqual(driver.current_window_handle, 'original')

    def test_incomplete_poll_is_bounded_and_keeps_only_actual_prices(self):
        m = self.api()
        with tempfile.TemporaryDirectory() as temp, patch.object(m, 'POLL_SECONDS', 0):
            driver = Driver(fixture().replace('>100.25</td>', '>-</td>', 1))
            result = m.collect_and_save(driver, Path(temp)/'partial.db', lambda: False, lambda message: None)
            self.assertEqual(result['status'], 'partial')
            self.assertEqual(result['rows'], 11)
            self.assertEqual(len(m.load_rows(Path(temp)/'partial.db')), 11)
            self.assertEqual(driver.current_window_handle, 'original')

    def test_cleanup_failure_returns_explicit_failure_and_still_restores_original(self):
        m = self.api()
        class CloseFails(Driver):
            def close(self):
                raise RuntimeError('owned close failed')
        with tempfile.TemporaryDirectory() as temp:
            driver = CloseFails(fixture())
            result = m.collect_and_save(driver, Path(temp)/'saved.db', lambda: False, lambda message: None)
            self.assertEqual(result['status'], 'failed')
            self.assertTrue(any('cleanup' in warning for warning in result['warnings']))
            self.assertEqual(driver.current_window_handle, 'original')

    def test_invalid_storage_batch_cannot_modify_existing_rows(self):
        m = self.api()
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp)/'prices.db'
            rows = m.parse(fixture(), CAPTURED)['rows']
            m.save_rows(db, rows)
            rows[0] = dict(rows[0], value='101.25')
            rows[-1] = dict(rows[-1], unit='USD/lb')
            with self.assertRaises(ValueError):
                m.save_rows(db, rows)
            self.assertEqual(next(row for row in m.load_rows(db) if row['instrument_id']=='LME_CU_CASH_BID')['value'], '100.25')

    def test_partial_crossed_cached_pair_rejects_entire_batch_without_revisions(self):
        m = self.api()
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp)/'prices.db'
            m.save_rows(db, m.parse(fixture(), CAPTURED)['rows'])
            before = m.load_rows(db)
            html = fixture().replace('>100.25</td>', '>200.25</td>', 1).replace('>110.25</td>', '>-</td>', 1)
            partial = m.parse(html, CAPTURED)['rows']
            self.assertEqual(len(partial), 11)
            partial[-1] = dict(partial[-1], value='131.25')
            with self.assertRaisesRegex(ValueError, 'Bid.*Ask'):
                m.save_rows(db, partial)
            self.assertEqual(m.load_rows(db), before)
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('SELECT count(*) FROM lme_official_revisions').fetchone()[0], 0)

    def test_valid_partial_updates_one_side_and_preserves_other_capture(self):
        m = self.api()
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp)/'prices.db'
            m.save_rows(db, m.parse(fixture(), CAPTURED)['rows'])
            html = fixture().replace('>100.25</td>', '>105.25</td>', 1).replace('>110.25</td>', '>-</td>', 1)
            partial = m.parse(html, '2026-10-27T11:00:00+09:00')['rows']
            self.assertEqual(m.save_rows(db, partial)['revised'], 1)
            self.assertEqual(m.save_rows(db, partial)['unchanged'], 11)
            rows = {row['side']: row for row in m.load_rows(db) if row['metal']=='Copper' and row['contract']=='Cash'}
            self.assertEqual(rows['Bid']['value'], '105.25')
            self.assertEqual(rows['Ask']['value'], '110.25')
            self.assertEqual(rows['Ask']['captured_at'], CAPTURED)
            self.assertEqual(rows['Bid']['captured_at'], '2026-10-27T11:00:00+09:00')
            with closing(sqlite3.connect(db)) as cx:
                self.assertEqual(cx.execute('SELECT count(*) FROM lme_official_revisions').fetchone()[0], 1)


if __name__=='__main__':
    unittest.main()
