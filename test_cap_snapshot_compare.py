"""Capture-to-capture comparisons are never official market-day closes."""
import json
import unittest


def capture(code,stamp,cap,rank=1,**changes):
    row=dict(stock_code=code,name='fixture '+code,rank=rank,market_date=None,
        captured_at=stamp,market_cap=cap,unit='원',currency='KRW',status='unverified',source_url='fixture://cap',
        raw_json=json.dumps(dict(market_scope='KRX_ALL',kind='live_ranking',market_cap_unit='억원',close_verified=False)))
    row.update(changes)
    return dict(entity='equities',entity_key=code,captured_at=stamp,raw_json=json.dumps(row))


class CaptureCompareTests(unittest.TestCase):
    def compare(self,rows):
        from cap_snapshot_compare import compare_captures
        return compare_captures(rows)

    def test_exact_decimal_pair_and_rank_move(self):
        result=self.compare([capture('005930','2026-10-26T08:30:00+09:00','100.1',3),
            capture('005930','2026-10-27T08:30:00+09:00','110.11',1)])
        self.assertEqual(len(result['columns']),15)
        row=result['rows'][0]
        self.assertEqual(row[:8],(1,'fixture 005930','005930',None,'110.11','억원','capture_pair','fixture://cap'))
        self.assertEqual(row[9:],('2026-10-26','100.1','10.01','10',3,2))

    def test_first_day_is_missing_prior_not_inferred(self):
        row=self.compare([capture('005490','2026-10-27T08:30:00+09:00','42',None)])['rows'][0]
        self.assertEqual(row[0],None)
        self.assertEqual(row[6],'missing_prior_capture')
        self.assertTrue(all(v is None for v in row[9:]))

    def test_kst_day_latest_capture_and_no_same_day_comparison(self):
        rows=[capture('005930','2026-10-26T23:40:00+00:00','10'),
            capture('005930','2026-10-27T09:30:00+09:00','11')]
        result=self.compare(rows)
        self.assertEqual(result['rows'][0][4],'11')
        self.assertEqual(result['rows'][0][6],'missing_prior_capture')

    def test_latest_cohort_does_not_forward_fill_dropped_top10(self):
        rows=[capture('005930','2026-10-26T08:30:00+09:00','10'),
            capture('000660','2026-10-27T08:30:00+09:00','11',1),
            capture('005490','2026-10-27T08:30:00+09:00','12',None)]
        result=self.compare(rows)
        self.assertEqual({r[2] for r in result['rows']},{'000660','005490'})
        self.assertTrue(all(r[6]=='missing_prior_capture' for r in result['rows']))

    def test_wrong_scope_scale_currency_and_naive_dates_rejected(self):
        rows=[capture('005930','2026-10-27T08:30:00+09:00','10',raw_json=json.dumps(dict(market_scope='KOSPI',kind='live_ranking',market_cap_unit='억원'))),
            capture('000660','2026-10-27T08:30:00+09:00','10',currency='USD'),
            capture('035420','2026-10-27T08:30:00+09:00','10',raw_json=json.dumps(dict(market_scope='KRX_ALL',kind='live_ranking',market_cap_unit='원'))),
            capture('005490','2026-10-27T08:30:00','10',None)]
        result=self.compare(rows)
        self.assertEqual(result['rows'],[])
        self.assertEqual(len(result['warnings']),4)

    def test_conflicting_exact_timestamp_quarantines_day_without_old_same_day_fallback(self):
        rows=[capture('005930','2026-10-27T07:30:00+09:00','9'),
            capture('005930','2026-10-27T08:30:00+09:00','10'),
            capture('005930','2026-10-27T08:30:00+09:00','11')]
        result=self.compare(rows)
        self.assertEqual(result['rows'],[])
        self.assertTrue(any('quarantined' in w for w in result['warnings']))

    def test_quarantined_previous_day_not_replaced_with_older_day(self):
        rows=[capture('005930','2026-10-23T08:30:00+09:00','8'),
            capture('005930','2026-10-26T08:30:00+09:00','9'),
            capture('005930','2026-10-26T08:30:00+09:00','10'),
            capture('005930','2026-10-27T08:30:00+09:00','11')]
        result=self.compare(rows)
        self.assertEqual(result['rows'][0][6],'missing_prior_capture')
        self.assertIsNone(result['rows'][0][10])

    def test_zero_prior_does_not_invent_percentage(self):
        result=self.compare([capture('005930','2026-10-26T08:30:00+09:00','0'),
            capture('005930','2026-10-27T08:30:00+09:00','10')])
        self.assertEqual(result['rows'][0][11],'10')
        self.assertIsNone(result['rows'][0][12])


if __name__=='__main__':unittest.main()
