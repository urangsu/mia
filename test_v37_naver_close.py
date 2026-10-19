"""Historical close selection contracts; synthetic observations, no live NAVER."""
import importlib.util
import unittest
from pathlib import Path

HERE=Path(__file__).parent


class CloseTests(unittest.TestCase):
    def module(self):
        target=HERE/'naver_close.py'
        self.assertTrue(target.exists(),'close selector missing')
        spec=importlib.util.spec_from_file_location('naver_close',target)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module

    def row(self,date,value,**kw):
        return dict(instrument_id='KOSPI',market_date=date,value=value,unit='포인트',
                    currency=None,status=kw.pop('status','final'),source_url='https://stock.naver.com/market',**kw)

    def test_830_kst_monday_uses_friday_and_thursday_not_calendar_subtraction(self):
        rows=[self.row('2026-10-16','110'),self.row('2026-10-15','100'),self.row('2026-10-19','130')]
        row=self.module().select_closes(rows,'2026-10-19T08:30:00+09:00')['rows'][0]
        self.assertEqual((row['previous_date'],row['prior_date']),('2026-10-16','2026-10-15'))
        self.assertEqual((row['previous_close'],row['prior_close'],row['change'],row['pct']),('110','100','10','10'))
        self.assertEqual(row['status'],'close_pair')

    def test_late_today_final_is_still_excluded_and_utc_cutoff_is_kst(self):
        rows=[self.row('2026-10-19','130'),self.row('2026-10-16','110'),self.row('2026-10-15','100')]
        result=self.module().select_closes(rows,'2026-10-19T14:00:00+00:00')
        self.assertEqual(result['cutoff_date'],'2026-10-19')
        self.assertEqual(result['rows'][0]['previous_date'],'2026-10-16')

    def test_conflicting_same_day_is_quarantined_not_latest_wins(self):
        rows=[self.row('2026-10-16','110'),self.row('2026-10-16','999'),self.row('2026-10-15','100'),self.row('2026-10-14','90')]
        result=self.module().select_closes(rows,'2026-10-19T08:30:00+09:00')
        self.assertEqual(result['rows'][0]['previous_date'],'2026-10-15')
        self.assertTrue(result['warnings'])

    def test_missing_second_never_uses_vendor_delta_to_invent_history(self):
        rows=[self.row('2026-10-16','110',change='10',pct='10')]
        row=self.module().select_closes(rows,'2026-10-19T08:30:00+09:00')['rows'][0]
        self.assertEqual(row['status'],'missing_history')
        self.assertIsNone(row['prior_close']);self.assertIsNone(row['change']);self.assertIsNone(row['pct'])

    def test_provisional_unverified_future_and_undated_excluded(self):
        rows=[self.row('2026-10-16','110',status='provisional'),self.row('2026-10-15','100',status='unverified'),self.row('2026-10-20','120'),self.row(None,'90')]
        row=self.module().select_closes(rows,'2026-10-19T08:30:00+09:00')['rows'][0]
        self.assertEqual(row['status'],'missing_history');self.assertIsNone(row['previous_close'])

    def test_stock_identity_and_zero_prior_are_retained_without_division(self):
        rows=[dict(stock_code='005490',market_date=d,price=v,status='stale',unit='원',currency='KRW',raw_json='{"close_verified":true}') for d,v in [('2026-10-16','100'),('2026-10-15','0')]]
        row=self.module().select_closes(rows,'2026-10-19T08:30:00+09:00')['rows'][0]
        self.assertEqual(row['stock_code'],'005490');self.assertEqual(row['change'],'100');self.assertIsNone(row['pct'])

    def test_duplicate_same_decimal_is_not_a_second_market_date(self):
        rows=[self.row('2026-10-16','110.0'),self.row('2026-10-16','110.00')]
        row=self.module().select_closes(rows,'2026-10-19T08:30:00+09:00')['rows'][0]
        self.assertEqual(row['status'],'missing_history')

    def test_futures_missing_history_and_unit_mismatch_are_not_approximated(self):
        rows=[dict(instrument_id='WTI',market_date='2026-10-16',value='60',status='final',unit='USD/bbl',currency='USD')]
        m=self.module()
        self.assertEqual(m.select_closes(rows,'2026-10-19T08:30:00+09:00')['rows'][0]['status'],'missing_history')
        rows.append(dict(rows[0],market_date='2026-10-15',value='50',unit='KRW/bbl',currency='KRW'))
        row=m.select_closes(rows,'2026-10-19T08:30:00+09:00')['rows'][0]
        self.assertEqual(row['status'],'missing_history');self.assertIsNone(row['pct'])

    def test_stale_age_is_not_source_close_evidence(self):
        m=self.module()
        rows=[self.row('2026-10-16','110',status='stale'),self.row('2026-10-15','100',status='stale')]
        self.assertEqual(m.select_closes(rows,'2026-10-19T08:30:00+09:00')['rows'][0]['status'],'missing_history')
        self.assertFalse(m.is_verified_close(rows[0]))
        rows[0]['raw_json']='{"close_verified":true}'
        rows[1]['close_verified']=True
        self.assertEqual(m.select_closes(rows,'2026-10-19T08:30:00+09:00')['rows'][0]['status'],'close_pair')


if __name__=='__main__':unittest.main()
