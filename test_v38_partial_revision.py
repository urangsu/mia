# -*- coding: utf-8 -*-
"""Regression: partial FMB corrections must not mix stale Mid with new range.

Company Excel/ECM is NOT touched by this offline integration fixture.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import ecm_excel_sync as ecm
import excel_secure
import FastmarketsCollector_v3_4 as core
import report_model

KEY='FMB|MB-LI-0029|$/kg|Actual|MID'
DAY='2026-10-16'
WIDGET='same-view'


def save(folder,low,mid,high):
    p=core.Price('MB-LI-0029',DAY,low,mid,high,None,'$/kg',
                 'Lithium carbonate battery grade cif CJK $/kg','Lithium','Actual','AG Grid',WIDGET)
    core.save_sqlite(core.path_bundle(Path(folder))['db'],[p],[],
        {'widget_count':1,'found_symbols':['MB-LI-0029'],'warnings':[]})


def snapshot(folder):
    return report_model.make_workbook_sheets(report_model.build_context(folder,end='2026-10-19'))


class PriceRevisionTests(unittest.TestCase):
    def test_partial_revision_clears_stale_mid_and_then_recovers(self):
        with tempfile.TemporaryDirectory() as folder:
            save(folder,'10','15','20')
            original=snapshot(folder)
            self.assertEqual(original['일별시세'][2][1],15000)
            save(folder,'30',None,'40')
            with sqlite3.connect(core.path_bundle(Path(folder))['db']) as cx:
                low,mid,high=cx.execute('SELECT low,mid,high FROM prices WHERE view_key=?',(WIDGET,)).fetchone()
                self.assertEqual((low,mid,high),('30',None,'40'))
                changes=cx.execute('SELECT COUNT(*) FROM price_revisions').fetchone()[0]
                self.assertEqual(changes,1)
            revised=snapshot(folder)
            self.assertEqual(revised['일별시세'][2][1],None)
            self.assertIn(('일별시세',DAY,KEY),
                          [r[:3] for r in revised['보류셀'][1:]])
            for sheet in ('일별시세','일별요약','월별시세'):
                plan=ecm.build_plan(revised[sheet],revised['가격열설정'],
                    original[sheet],original['가격열설정'],
                    period_type='monthly' if sheet.startswith('월별') else 'daily',
                    clear_cells=excel_secure.quarantined_cells(revised,sheet))
                self.assertEqual(plan['stats']['cleared'],1,sheet)
                self.assertIsNone(plan['edits'][0]['incoming'])
            # Identical second fetch does not manufacture a second revision.
            save(folder,'30',None,'40')
            with sqlite3.connect(core.path_bundle(Path(folder))['db']) as cx:
                self.assertEqual(cx.execute('SELECT COUNT(*) FROM price_revisions').fetchone()[0],1)
            save(folder,'30','35','40')
            recovered=snapshot(folder)
            self.assertEqual(recovered['일별시세'][2][1],35000)
            plan=ecm.build_plan(recovered['일별시세'],recovered['가격열설정'],
                revised['일별시세'],revised['가격열설정'])
            self.assertEqual(plan['edits'][0]['incoming'],35000)
            self.assertFalse(plan['new_columns'])

    def test_unquoted_first_day_does_not_create_false_withdrawal(self):
        from excel_secure import make_sheets
        from smbs_rates import prepare_excel_series
        from dataclasses import replace
        empty=core.Price('MB-LI-0029',DAY,'10',None,'20',None,'$/kg',
            'Lithium carbonate','Lithium','Actual','AG Grid','first')
        quoted=replace(empty,date='2026-10-19',mid='15')
        warnings=[];quarantined=[]
        rows=prepare_excel_series([empty,quoted],[],issues=warnings,quarantined=quarantined)
        self.assertNotIn(DAY,rows)
        self.assertFalse(quarantined)
        sheets=make_sheets([empty,quoted],[],[])
        self.assertEqual([r[0] for r in sheets['일별시세'][2:]],['2026-10-19'])
        self.assertEqual(sheets['월별건수'][2][1],1)

    def test_legacy_stale_mid_outside_range_is_not_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            # Legacy COALESCE may already have saved the impossible tuple.
            save(folder,'30','15','40')
            result=snapshot(folder)
            self.assertIsNone(result['일별시세'][2][1])
            self.assertTrue(any('Low/Mid/High' in str(r) for r in result['보류셀'][1:]))

    def test_valid_mid_only_replacement_removes_stale_range(self):
        with tempfile.TemporaryDirectory() as folder:
            save(folder,'10','15','20')
            save(folder,None,'22',None)
            with sqlite3.connect(core.path_bundle(Path(folder))['db']) as cx:
                data=cx.execute('SELECT low,mid,high FROM prices').fetchone()
                self.assertEqual(data,(None,'22',None))
            self.assertEqual(snapshot(folder)['일별시세'][2][1],22000)


if __name__=="__main__":
    unittest.main()
