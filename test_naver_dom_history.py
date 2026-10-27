"""Synthetic HTML only, not company browser acceptance."""
import importlib
import json
from pathlib import Path
import unittest

CAPTURED = '2026-10-27T10:00:00+09:00'
STOCK = 'https://stock.naver.com/domestic/stock/005930/price'


def table(rows, headers=('날짜', '종가', '전일대비', '시가', '고가', '저가', '거래량', '거래대금')):
    return '<table><thead><tr>' + ''.join('<th>'+h+'</th>' for h in headers) + '</tr></thead><tbody>' + ''.join(
        '<tr><td>'+date+'</td><td><span class="SingleLinePrice_price__fixture">'+price+'</span></td><td>하락 999</td></tr>'
        for date, price in rows) + '</tbody></table>'


class DailyHistoryTests(unittest.TestCase):
    def parse(self, html, instrument_id='005930', source_url=STOCK, **kwargs):
        self.assertTrue(Path(__file__).with_name('naver_dom_history.py').is_file(), 'DOM history parser missing')
        return importlib.import_module('naver_dom_history').parse_daily_history(
            html, instrument_id, source_url, captured_at=kwargs.pop('captured_at', CAPTURED),
            equity=kwargs.pop('equity', True), **kwargs)

    def test_stock_daily_rows_use_explicit_closes_without_marketcap_or_rank(self):
        result = self.parse(table([('26. 10. 27.', '9,999'), ('26. 10. 26.', '<span>1,</span><span>100</span>'),
                                   ('26. 10. 23.', '1,000')]), name='합성기업')
        self.assertEqual([r['market_date'] for r in result['rows']], ['2026-10-26', '2026-10-23'])
        row = result['rows'][0]
        self.assertEqual((row['stock_code'], row['price'], row['unit'], row['currency']), ('005930', '1100', '원', 'KRW'))
        self.assertEqual(row['name'], '합성기업')
        self.assertIsNone(row['rank'])
        self.assertIsNone(row['market_cap'])
        self.assertIsNone(row['change'])
        self.assertIsNone(row['pct'])
        self.assertEqual(row['status'], 'stale')
        self.assertEqual(row['source_url'], STOCK)
        raw = json.loads(row['raw_json'])
        self.assertIs(raw['close_verified'], True)
        self.assertEqual(raw['table_source'], 'NAVER KRX 일별 시세')
        self.assertEqual(result['warnings'], [])

    def test_index_four_digit_year_and_parameterized_units(self):
        result = self.parse(table([('2026. 10. 26.', '2,100.25'), ('2026. 10. 23.', '2,000.50')]),
                            'KOSPI', 'https://stock.naver.com/domestic/index/KOSPI/price', equity=False)
        row = result['rows'][0]
        self.assertEqual((row['instrument_id'], row['value'], row['unit'], row['currency']),
                         ('KOSPI', '2100.25', '포인트', None))
        self.assertNotIn('stock_code', row)

    def test_wrong_identity_or_origin_never_binds_prices(self):
        html = table([('26. 10. 26.', '100')])
        for url in (STOCK.replace('005930', '005490'), STOCK.replace('stock.naver.com', 'evil.example'),
                    STOCK.replace('/price', '/total'), 'https://stock.naver.com@evil.example/domestic/stock/005930/price'):
            with self.subTest(url=url):
                result = self.parse(html, source_url=url)
                self.assertEqual(result['rows'], [])
                self.assertTrue(result['warnings'])

    def test_observed_world_index_identities_and_custom_units(self):
        html = table([('2026.10.26.', '110.25'), ('2026.10.23.', '100.25')])
        for identity, code in [('NASDAQ', '.IXIC'), ('SP500', '.INX')]:
            result = self.parse(html, identity, 'https://stock.naver.com/worldstock/index/'+code+'/price',
                                equity=False, unit='points', currency=None)
            self.assertEqual(len(result['rows']), 2)
            self.assertEqual(result['rows'][0]['unit'], 'points')
        wrong = self.parse(html, 'NASDAQ', 'https://stock.naver.com/worldstock/index/.INX/price', equity=False)
        self.assertEqual(wrong['rows'], [])

    def test_gold_recent_contract_never_becomes_points_or_continuous_futures(self):
        url = 'https://stock.naver.com/marketindex/metals/GCcv1/price'
        html = table([('2026.10.26.', '110.25'), ('2026.10.23.', '100.25')],
                     ('날짜', '종가', '전일대비', '등락률'))
        result = self.parse(html, 'GOLD', url, equity=False, unit='USD/트로이온스', currency='USD')
        self.assertEqual(len(result['rows']), 2)
        row = result['rows'][0]
        self.assertEqual((row['unit'], row['currency']), ('USD/트로이온스', 'USD'))
        raw = json.loads(row['raw_json'])
        self.assertEqual(raw['table_source'], 'NAVER COMEX 금선물 최근월물 일별 시세')
        self.assertEqual(raw['contract_code'], 'GCcv1')
        self.assertEqual(raw['price_type'], 'recent_contract_futures')
        missing_unit = self.parse(html, 'GOLD', url, equity=False)
        self.assertEqual(missing_unit['rows'], [])
        self.assertTrue(missing_unit['warnings'])

    def test_wti_recent_contract_requires_barrel_unit_and_retains_nymex_identity(self):
        url = 'https://stock.naver.com/marketindex/energy/CLcv1/price'
        html = table([('2026.10.26.', '110.25'), ('2026.10.23.', '100.25')],
                     ('날짜', '종가', '전일대비', '등락률'))
        result = self.parse(html, 'WTI', url, equity=False, unit='USD/bbl', currency='USD')
        self.assertEqual(len(result['rows']), 2)
        row = result['rows'][0]
        self.assertEqual((row['unit'], row['currency']), ('USD/bbl', 'USD'))
        raw = json.loads(row['raw_json'])
        self.assertEqual(raw['table_source'], 'NAVER NYMEX WTI선물 최근월물 일별 시세')
        self.assertEqual(raw['contract_code'], 'CLcv1')
        self.assertEqual(raw['price_type'], 'recent_contract_futures')
        self.assertEqual(self.parse(html, 'WTI', url, equity=False)['rows'], [])
        wrong_unit = self.parse(html, 'WTI', url, equity=False, unit='USD/oz', currency='USD')
        self.assertEqual(wrong_unit['rows'], [])

    def test_bond_yields_keep_percent_units_and_strict_country_identity(self):
        html = table([('2026.10.26.', '3.25'), ('2026.10.23.', '3.20')],
                     ('날짜', '종가', '전일대비', '등락률'))
        for identity, code, country in [('US10Y', 'US10YT=RR', '미국'), ('KR10Y', 'KR10YT=RR', '한국')]:
            with self.subTest(identity=identity):
                url = 'https://stock.naver.com/marketindex/bond/'+code+'/price'
                result = self.parse(html, identity, url, equity=False, unit='%', currency=None)
                self.assertEqual(len(result['rows']), 2)
                row = result['rows'][0]
                self.assertEqual((row['value'], row['unit'], row['currency']), ('3.25', '%', None))
                raw = json.loads(row['raw_json'])
                self.assertEqual(raw['price_type'], 'government_bond_yield')
                self.assertEqual(raw['table_source'], 'NAVER '+country+' 국채10년 수익률 일별 시세')
                wrong = 'KR10Y' if identity == 'US10Y' else 'US10Y'
                self.assertEqual(self.parse(html, wrong, url, equity=False, unit='%')['rows'], [])
                self.assertEqual(self.parse(html, identity, url, equity=False, unit='포인트')['rows'], [])

    def test_headers_must_be_same_table_and_exact_not_current_price(self):
        for html in (table([('26. 10. 26.', '100')], ('날짜', '현재가')),
                     '<p>날짜 종가 2026.10.26</p><table><tr><td>26.10.26.</td><td>100</td></tr></table>',
                     '<table><tr><th>날짜</th></tr></table><table><tr><th>종가</th></tr><tr><td>26.10.26.</td><td>100</td></tr></table>'):
            result = self.parse(html)
            self.assertEqual(result['rows'], [])
            self.assertTrue(result['warnings'])

    def test_top_page_date_cannot_fill_undated_row_and_invalid_values_skipped(self):
        html = '<time>2026.10.26</time>' + table([('', '100'), ('26. 02. 30.', '100'),
            ('26. 10. 28.', '100'), ('26. 10. 26.', '-'), ('26.10.23.', '0')])
        result = self.parse(html)
        self.assertEqual(result['rows'], [])
        self.assertTrue(result['warnings'])

    def test_same_day_conflicting_closes_are_both_rejected(self):
        result = self.parse(table([('26.10.26.', '100'), ('26.10.26.', '200'),
                                   ('26.10.26.', '100'), ('26.10.23.', '90')]))
        self.assertEqual([r['market_date'] for r in result['rows']], ['2026-10-23'])
        self.assertTrue(any('conflict' in w for w in result['warnings']))
        self.assertTrue(any('pair' in w for w in result['warnings']))

    def test_equal_duplicates_deduplicated_and_one_valid_row_allowed(self):
        result = self.parse(table([('26.10.26.', '100'), ('26.10.26.', '100.00')]))
        self.assertEqual(len(result['rows']), 1)
        self.assertTrue(any('pair' in w for w in result['warnings']))

    def test_captured_timestamp_uses_kst_calendar_not_utc_day(self):
        result = self.parse(table([('26.10.27.', '100'), ('26.10.26.', '90')]),
                            captured_at='2026-10-26T16:00:00+00:00')
        self.assertEqual([r['market_date'] for r in result['rows']], ['2026-10-26'])


if __name__ == '__main__':
    unittest.main()
