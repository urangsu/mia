# -*- coding: utf-8 -*-
"""Focused offline regression for v3.8 conversion, Westmetall and report layout."""
import sqlite3
import unittest
from types import SimpleNamespace

from smbs_rates import prepare_excel_series
from westmetall_lme import parse_table, persist, WestmetallError
from lme_reporting import add_lme_sheets, build_business_tables, report_unit

FAKE_HTML = """<table>
<tr><th>date</th><th>LME Nickel Cash-Settlement</th><th>LME Nickel 3-month</th><th>LME Nickel stock</th></tr>
<tr><td>19. October 2026</td><td>15,275.00</td><td>15,490.00</td><td>280,110</td></tr>
<tr><td>16. October 2026</td><td>15,310.00</td><td>15,500.00</td><td>280,230</td></tr>
</table>"""

def price(mid,view,unit="$/lb",code="MB-CO-0005",day="2026-10-19"):
    return SimpleNamespace(price_mode="Actual",period_label="",
        date=day,symbol=code,unit=unit,low=None,mid=mid,high=None,view_key=view)


class LmeAndUnitTests(unittest.TestCase):
    def test_cobalt_lb_and_tonne_views_reconcile_to_one_report_value(self):
        issues=[]
        rows=prepare_excel_series([price("22.50","original"),price("49604.01","converted")],[],
            issues=issues)
        self.assertEqual(rows["2026-10-19"]["FMB|MB-CO-0005|$/lb|Actual|MID"],49604.01)
        self.assertFalse(issues)

    def test_cobalt_converted_only_quarantined(self):
        issues=[]
        rows=prepare_excel_series([price("49604.01","converted")],[],issues=issues)
        self.assertFalse(rows.get("2026-10-19"))
        self.assertTrue(any("원본" in s for s in issues))

    def test_cobalt_mismatched_tonne_rejected(self):
        issues=[]
        rows=prepare_excel_series([price("22.50","original"),price("49000","wrong")],[],issues=issues)
        self.assertNotIn("FMB|MB-CO-0005|$/lb|Actual|MID",rows.get("2026-10-19",{}))
        self.assertTrue(issues)

    def test_lithium_kg_report_tonne_and_original_untouched(self):
        p=price("21.45","lc","$/kg","MB-LI-0029")
        rows=prepare_excel_series([p],[])
        self.assertEqual(rows["2026-10-19"]["FMB|MB-LI-0029|$/kg|Actual|MID"],21450)
        self.assertEqual(p.mid,"21.45")
        self.assertEqual(report_unit("FMB|MB-LI-0029|$/kg|Actual|MID","$/kg"),"USD/tonne")

    def test_lme_html_dates_cash_three_month_and_stock(self):
        rows=parse_table(FAKE_HTML,"NI","https://example.com",cutoff="2026-10-16")
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[-1]["cash_usd_t"],15275)
        self.assertEqual(rows[-1]["three_month_usd_t"],15490)
        self.assertEqual(rows[-1]["stock_t"],280110)

    def test_lme_html_wrong_header_fails_closed(self):
        with self.assertRaises(WestmetallError):
            parse_table(FAKE_HTML.replace("Nickel","Copper"),"NI")

    def test_lme_idempotent_revision_audited(self):
        rows=parse_table(FAKE_HTML,"NI","https://example.com")
        with sqlite3.connect(":memory:") as cx:
            self.assertEqual(persist(cx,rows)["inserted"],2)
            self.assertEqual(persist(cx,rows)["unchanged"],2)
            revised=[dict(x) for x in rows];revised[-1]["cash_usd_t"]=15276
            self.assertEqual(persist(cx,revised)["updated"],1)
            self.assertEqual(cx.execute("SELECT COUNT(*) FROM lme_revision_history").fetchone()[0],1)

    def test_append_columns_and_five_days(self):
        base=[("고시일","LC"),("","FMB"),("2026-10-16",21450.0),("2026-10-19",21500.0)]
        month=[("기준월","LC"),("","FMB"),("2026-10",21475.0)]
        sheets={"일별시세":list(base),"일별요약":list(base),"월별시세":list(month),
                "월별건수":[("기준월","LC"),("","FMB"),("2026-10",2)],
                "가격열설정":[("key","label","source"),("FMB|MB-LI-0029|$/kg|Actual|MID","LC","FMB")]}
        data=parse_table(FAKE_HTML,"NI","https://example.com")
        add_lme_sheets(sheets,data)
        self.assertEqual(sheets["일별시세"][1][-6:],
            ("WESTMETALL",)*6)
        self.assertEqual(sheets["일별시세"][-1][2],15275.0)
        self.assertIn("LME_원본",sheets)
        tbl=build_business_tables(sheets,report_end="2026-10-19")
        self.assertIn("보고용_최근5일",tbl)
        self.assertIn("보고용_3개월평균",tbl)
        self.assertTrue(any("전 고시 比" in r[1] for r in tbl["보고용_문구"][1:]))

if __name__=="__main__":
    unittest.main()
