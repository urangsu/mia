import unittest
from naver_dom_history import parse_daily_history

class RateTests(unittest.TestCase):
    def test_observed_rate_routes_accept_daily_tables_with_explicit_units(self):
        html='<table><tr><th>날짜</th><th>종가</th></tr><tr><td>2026.10.29.</td><td>4.449</td></tr><tr><td>2026.10.28.</td><td>4.481</td></tr></table>'
        for code,path in [('KR3Y','bond/KR3YT=RR'),('KR_CORP_AA_3Y','domesticInterest/KFIA103009')]:
            url='https://stock.naver.com/marketindex/'+path+'/price'
            result=parse_daily_history(html,code,url,captured_at='2026-10-30T08:30:00+09:00',unit='%')
            self.assertEqual(len(result['rows']),2)
            self.assertFalse(parse_daily_history(html,code,url,captured_at='2026-10-30T08:30:00+09:00')['rows'])

