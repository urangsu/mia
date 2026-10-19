# -*- coding: utf-8 -*-
import importlib
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
import excel_secure as excel
import FastmarketsCollector_v3_4 as fm

class TestV354Fixes(unittest.TestCase):
    def test_optional_visual_safely_skips_locked_format(self):
        log=[]
        def blocked():raise RuntimeError('company policy denied NumberFormat')
        self.assertFalse(excel._optional_visual(blocked,'A열',log.append))
        self.assertIn('NumberFormat',log[0])
        self.assertTrue(excel._optional_visual(lambda:None,'A열',log.append))

    def test_all_headers_with_gridcells_needs_no_drag(self):
        good={'headerIds':['date','MB-BMS-0012-mid','MB-BMS-0001-mid'],
              'visibleIds':['date','MB-BMS-0012-mid','MB-BMS-0001-mid']}
        self.assertTrue(fm.grid_columns_materialized(good))
        good['visibleIds'].remove('MB-BMS-0001-mid')
        self.assertFalse(fm.grid_columns_materialized(good))
        self.assertFalse(fm.grid_columns_materialized({'headerIds':['date'],'visibleIds':['date']}))

    def test_default_excel_target_when_none(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(fm.path_bundle(Path(t))['xlsx'],Path(t)/'fastmarkets_prices.xlsx')

    def test_bm_mapping_probe_counters(self):
        w={'title':'BM(원료) Payable', 'mode':'Actual', 'headers':[{'code':'MB-BMS-0012','description':
          'Black mass, NCM, high cobalt, inferred, cif South Korea, $/tonne'}],
          'directCodes':['MB-BMS-0012'],
          'grids':[{'index':'0','rows':[{'index':0,'cells':[
            {'colId':'date','text':'16 Oct 2026'},
            {'colId':'MB-BMS-0012-mid','text':'8,542.15','title':'8,542.15'}
          ]}]}], 'chartRows':[]}
        from datetime import date
        prices,inventory,warnings=fm.read_snapshot({'widgets':[w]},31,now=date(2026,10,19))
        self.assertEqual(len(prices),1)
        self.assertEqual(prices[0].mid,'8542.15')
        self.assertEqual(inventory[0]['parse_stats']['rows_accepted'],1)
        self.assertFalse([x for x in warnings if '가격 없는' in x])

if __name__=='__main__':unittest.main()
