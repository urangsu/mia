# -*- coding: utf-8 -*-
"""Synthetic-only AG Grid virtual viewport regression contracts.

Derived from the public AG Grid documentation's row/column virtualization model.
No authenticated page HTML, cookie, authorization header or company data stored.
"""
import unittest
import FastmarketsCollector_v3_4 as core


class VirtualGridContracts(unittest.TestCase):
    def test_bm_date_and_mid_are_scoped_to_the_same_widget_grid(self):
        sample = {"grids":[
            {"index":"0","rows":[
                {"index":0,"cells":[
                    {"colId":"date","text":"19 Oct 2026"},
                    {"colId":"MB-BMS-0012-mid","text":"8542.15"},
                    {"colId":"MB-BMS-0001-mid","text":"65.2"}]},
                {"index":1,"cells":[
                    {"colId":"date","text":"16 Oct 2026"},
                    {"colId":"MB-BMS-0001-mid","text":"64.9"}]}
            ]},
            {"index":"1","rows":[{"index":0,"cells":[
                {"colId":"date","text":"01 Sep 2026"},
                {"colId":"MB-LI-0029-mid","text":"13.75"}]}]}
        ]}
        self.assertEqual(core.oldest_visible_price_date(sample,0),"2026-10-16")
        self.assertEqual(core.oldest_visible_price_date(sample,1),"2026-09-01")
        self.assertIsNone(core.oldest_visible_price_date(sample,2))

    def test_missing_virtual_date_must_not_guess_collection_date(self):
        # A screen can contain all six BMS price column IDs but none of their
        # date cells. It is *not* proof of a complete dated observation.
        sample={"grids":[{"index":0,"rows":[{"index":0,"cells":[
            {"colId":"MB-BMS-0012-mid","text":"8542.15"},
            {"colId":"MB-BMS-0001-mid","text":"65.2"},
            {"colId":"MB-BMS-0002-mid","text":"72.1"},
            {"colId":"MB-BMS-0003-mid","text":"34.8"},
            {"colId":"MB-BMS-0010-mid","text":"68.2"},
            {"colId":"MB-BMS-0011-mid","text":"29.1"}]}]}]}
        self.assertIsNone(core.oldest_visible_price_date(sample,0))

    def test_invalid_rendered_dates_do_not_become_zero_or_today(self):
        sample={"grids":[{"index":0,"rows":[
            {"index":0,"cells":[{"colId":"date","text":"Loading..."}]},
            {"index":1,"cells":[{"colId":"date","text":"No data"}]},
            {"index":2,"cells":[{"colId":"date","text":"19 Oct 2026"}]}
        ]}]}
        self.assertEqual(core.oldest_visible_price_date(sample,0),"2026-10-19")

    def test_daily_history_budget_stays_bounded(self):
        offsets,all_history=core.daily_vertical_positions(150000,250,7)
        self.assertLessEqual(len(offsets),18)
        self.assertFalse(all_history)
        _,all_history=core.daily_vertical_positions(150000,250,0)
        self.assertTrue(all_history)


if __name__=="__main__":
    unittest.main()
