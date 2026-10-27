import json
import unittest
from naver_markets import parse_capitalization


class CurrentCapDOMTests(unittest.TestCase):
    def page(self, scope='true'):
        return f'''<div role="button"><span class="a11y">시장 레벨 토글, 총 2단계 중 1번째</span><span>KRX</span></div><button role="radio" aria-checked="{scope}">전체</button>
        <table><caption>국내 종목 주식 테이블</caption><thead><tr>
        <th>종목명</th><th>현재가</th><th>전일대비</th><th>거래량</th>
        <th>거래대금</th><th>고가</th><th>저가</th><th>시가총액</th></tr></thead><tbody>
        <tr role="button"><td><button>관심종목에 추가</button><span class="index">1</span>
        <img src="https://ssl.pstatic.net/imgstock/fn/real/logo/stock/Stock005930.svg" alt="테스트전자 로고">테스트전자</td>
        <td><span class="SingleLinePrice_price__x">12<span>3,000</span></span><span role="status">가격이 업데이트되었습니다</span></td>
        <td><span>상승3,000</span><span>(+2.50%)</span></td>
        <td>10주</td><td>20백만</td><td>130,000</td><td>120,000</td><td>12조 3,456억</td></tr>
        </tbody></table>'''

    def test_current_rows_preserve_identity_scale_and_undated_status(self):
        rows=parse_capitalization(self.page(),'2026-10-27T08:30:00+09:00')['rows']
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual((row['stock_code'],row['name'],row['rank']),('005930','테스트전자',1))
        self.assertEqual((row['price'],row['market_cap']),('123000','123456'))
        self.assertEqual(json.loads(row['raw_json'])['market_cap_unit'],'억원')
        self.assertIsNone(row['market_date'])
        self.assertEqual(row['status'],'unverified')
        self.assertFalse(json.loads(row['raw_json'])['close_verified'])

    def test_non_all_scope_does_not_create_top_ten(self):
        self.assertEqual(parse_capitalization(self.page('false'))['rows'],[])

    def test_partially_hydrated_row_does_not_crash_parser(self):
        page=self.page().replace('<td>12조 3,456억</td>','')
        result=parse_capitalization(page)
        self.assertEqual(result['rows'],[])
        self.assertTrue(result['warnings'])

    def test_consensus_date_never_dates_live_ranking(self):
        page=self.page()+'<p>2026.10.26. 기준 에프앤가이드 컨센서스</p>'
        self.assertIsNone(parse_capitalization(page)['rows'][0]['market_date'])


if __name__=='__main__': unittest.main()
