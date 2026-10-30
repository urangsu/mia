import unittest
from types import SimpleNamespace

class EquityTests(unittest.TestCase):
    def test_stock_cap_and_close_join_requires_identity_and_day(self):
        from report_presentation import equity_table
        context=SimpleNamespace(tables={
            '보고용_시총':[('순위','종목명','코드','시장일','시가총액','단위','출처'),(1,'합성기업','005930','2026-10-29',1000,'억원','https://stock.naver.com/')],
            '보고용_주가':[('종목명','코드','시장일','수치','전일대비','등락률(%)','단위'),('합성기업','005930','2026-10-29',110,10,10,'원')]})
        table=equity_table(context)
        self.assertEqual(table['headers'],('순위','종목','시가총액','주가','등락(등락률)'))
        self.assertEqual(table['rows'][0][3]['text'],'110 원')
        self.assertEqual(table['rows'][0][4]['text'],'+10 원 (+10.0%)')
        context.tables['보고용_주가'][1]=('합성기업','005930','2026-10-28',99,1,1,'원')
        self.assertEqual(equity_table(context)['rows'][0][3]['text'],'—')
