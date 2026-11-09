import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

class EquityTests(unittest.TestCase):
    def test_top_ten_logos_and_posco_when_its_market_data_is_missing(self):
        from report_presentation import equity_table
        headers=('순위','종목명','코드','시가총액','단위')
        codes=('005930','000660','005935','402340','373220','009150',
               '207940','005380','105560','068270')
        caps=[(rank,code,code,1000,'억원') for rank,code in enumerate(codes,1)]
        context=SimpleNamespace(tables={'보고용_시총':[headers,*caps]})
        rows=equity_table(context)['rows']
        self.assertEqual(len(rows),11)
        for row,code in zip(rows,(*codes,'005490')):
            self.assertTrue(row[1]['logo'].endswith(f'Stock{code}.svg'))
        self.assertEqual(rows[-1][1]['text'],'POSCO홀딩스')
        self.assertTrue(all(rows[-1][i]['text']=='—' for i in (0,2,3,4)))

    def test_stock_logos_follow_the_ticker_not_the_rank(self):
        from report_presentation import equity_table
        context=SimpleNamespace(tables={'보고용_시총':[
            ('순위','종목명','코드','시가총액','단위'),
            (2,'삼성전자','005930',1000,'억원'),
            (1,'SK하이닉스','000660',2000,'억원'),
            (None,'POSCO홀딩스','005490',300,'억원'),
            (4,'코드 미확인','005490.svg?data=secret',250,'억원')]})
        rows=equity_table(context)['rows']
        self.assertEqual([r[1].get('logo') for r in rows],[
            'https://ssl.pstatic.net/imgstock/fn/real/logo/stock/Stock005930.svg',
            'https://ssl.pstatic.net/imgstock/fn/real/logo/stock/Stock000660.svg',
            'https://ssl.pstatic.net/imgstock/fn/real/logo/stock/Stock005490.svg',None])

    def test_html_logo_is_decorative_and_keeps_the_name_link(self):
        from report_exports import export_html
        from test_report_presentation import sample_context
        with TemporaryDirectory() as folder:
            path=Path(folder)/'report.html'
            export_html(sample_context(),path)
            body=path.read_text(encoding='utf-8').split('id="caps"',1)[1].split('</section>',1)[0]
        self.assertIn('src="https://ssl.pstatic.net/imgstock/fn/real/logo/stock/Stock005930.svg"',body)
        self.assertIn('alt=""',body)
        self.assertIn('loading="lazy"',body)
        self.assertIn('referrerpolicy="no-referrer"',body)
        self.assertIn('crossorigin="anonymous"',body)
        self.assertIn('>삼성전자</span>',body)

    def test_stock_cap_and_close_join_requires_identity_and_day(self):
        from report_presentation import equity_table
        context=SimpleNamespace(tables={
            '보고용_시총':[('순위','종목명','코드','시장일','시가총액','단위','출처'),(1,'합성기업','005930','2026-10-29',1000,'억원','https://stock.naver.com/')],
            '보고용_주가':[('종목명','코드','시장일','수치','전일대비','등락률(%)','단위'),('합성기업','005930','2026-10-29',110,10,10,'원')]})
        table=equity_table(context)
        self.assertEqual(table['headers'],('순위','종목','시가총액','주가','등락(등락률)'))
        self.assertEqual(table['rows'][0][3]['text'],'110 원')
        self.assertEqual(table['rows'][0][4]['text'],'+10 원 (+10.0%)')
        self.assertIn('시총 기준일 2026.10.29 · 주가 종가 2026.10.29',table['subtitle'])
        context.tables['보고용_주가'][1]=('합성기업','005930','2026-10-28',99,1,1,'원')
        self.assertEqual(equity_table(context)['rows'][0][3]['text'],'—')
