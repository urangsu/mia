# -*- coding: utf-8 -*-
"""Contract tests with user-provided HTML/values (no live Fastmarkets credentials)."""
import csv
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path

SOURCE=Path(__file__).with_name('FastmarketsCollector_v3_4.py')
spec=importlib.util.spec_from_file_location('fmv3',str(SOURCE))
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)


class Tests(unittest.TestCase):
    def sample(self):
        return {"url":m.WORKSPACE_URL,"widgets":[
            {"title":"탄산리튬", "mode":"Actual","directCodes":["MB-LI-0029"],
             "headers":[],"unit":"US Dollar / Kilogram",
             "chartRows":[{"date":"15 Oct 2026","priceTitle":"14.00 - 15.60","change":"-5.13%"}],"grids":[],"scrollCaps":[]},
            {"title":"FMB 수산화리튬", "mode":"Actual", "directCodes":["MB-LI-0033"],
             "headers":[{"code":"MB-LI-0033","description":"Lithium hydroxide, $/kg"}],
             "grids":[{"index":"0","rows":[{"index":0,"cells":[
                {"colId":"Date","text":"15 Oct 2026"},
                {"colId":"MB-LI-0033-low","text":"14.00","title":"14.00"},
                {"colId":"MB-LI-0033-mid","text":"14.80","title":"14.80"},
                {"colId":"MB-LI-0033-high","text":"15.60","title":"15.60"}]}]}],"chartRows":[],"scrollCaps":[]},
            {"title":"BM Payable", "mode":"Monthly Average", "directCodes":[],
             "headers":[
                 {"code":"MB-BMS-0012","description":"Black mass, NCM, high cobalt, inferred, cif South Korea, $/tonne"},
                 {"code":"MB-BMS-0001","description":"Black mass, NCM, payable indicator, nickel, max 5% moisture, cif South Korea, % payable LME Nickel cash official price"},
                 {"code":"MB-BMS-0002","description":"Black mass, NCM, payable indicator, cobalt, max 5% moisture, cif South Korea, % payable cobalt"}],
             "grids":[{"index":"0","rows":[{"index":0,"cells":[
                 {"colId":"date","text":"1 Oct - 16 Oct 2026"},
                 {"colId":"MB-BMS-0012-mid","text":"7669.67","title":"7669.67"},
                 {"colId":"MB-BMS-0001-mid","text":"94.75","title":"94.75"},
                 {"colId":"MB-BMS-0002-mid","text":"68.20","title":"68.20"}]}]}],"chartRows":[],"scrollCaps":[]},
             {"title":"코발트", "mode":"Actual", "directCodes":["MB-CO-0004"],
              "headers":[{"code":"MB-CO-0004","description":"Cobalt standard grade, in-whs Rotterdam, $/lb"}],
              "grids":[{"index":"0","rows":[{"index":0,"cells":[
                {"colId":"date","text":"15 Oct 2026"},
                {"colId":"MB-CO-0004-low","text":"22.00"},
                {"colId":"MB-CO-0004-mid","text":"23.50"}]}]}],"chartRows":[],"scrollCaps":[]},
             {"title":"망간", "mode":"Actual", "directCodes":["MB-MN-0001"],
              "headers":[{"code":"MB-MN-0001","description":"Manganese 99.7% electrolytic manganese flake, $/tonne"}],
              "grids":[{"index":"0","rows":[{"index":0,"cells":[
                {"colId":"date","text":"15 Oct 2026"},
                {"colId":"MB-MN-0001-mid","text":"2775.00"}]}]}],"chartRows":[],"scrollCaps":[]}]
            }

    def test_date_and_number(self):
        self.assertEqual(m.normalize_date('15 Oct 2026'), '2026-10-15')
        self.assertEqual(m.period_end('1 Oct - 16 Oct 2026'),'2026-10-16')
        self.assertEqual(m.normalize_number('51,808.63'),'51808.63')
        self.assertEqual(m.normalize_number('-5.13%'),'-5.13')
        self.assertIsNone(m.normalize_number('—'))

    def test_chart_grid_period_and_metadata(self):
        prices, inventory, warnings=m.read_snapshot(self.sample(),365,now=date(2026,10,16))
        self.assertEqual(len(prices),7)
        chart=next(p for p in prices if p.symbol=='MB-LI-0029')
        self.assertEqual((chart.low,chart.mid,chart.high,chart.change_pct),('14.00',None,'15.60','-5.13'))
        hydro=next(p for p in prices if p.symbol=='MB-LI-0033')
        self.assertEqual((hydro.low,hydro.mid,hydro.high,hydro.unit),('14.00','14.80','15.60','$/kg'))
        black=next(p for p in prices if p.symbol=='MB-BMS-0012')
        self.assertEqual((black.mid,black.period_label,black.unit,black.date),('7669.67','1 Oct - 16 Oct 2026','$/tonne','2026-10-16'))
        self.assertEqual(len(inventory),5)
        self.assertFalse(warnings)

    def test_no_fake_prices_without_date(self):
        w=self.sample()["widgets"][2]
        w["grids"][0]["rows"][0]["cells"][0]["text"]=""
        prices,inventory,warnings=m.read_snapshot({"widgets":[w]},365,now=date(2026,10,16))
        self.assertEqual(prices,[])
        self.assertTrue(warnings)

    def test_merge_virtualized_horizontal_and_vertical(self):
        original={"title":"Payable", "directCodes":[],"headers":[],"mode":"Actual", "chartRows":[],"grids":[{"index":"0","rows":[
            {"index":0,"cells":[{"colId":"date","text":"15 Oct 2026"},{"colId":"MB-BMS-0001-mid","text":"94.75"}]}]}]}
        extra={"title":"Payable", "directCodes":[],"headers":[{"code":"MB-BMS-0002","description":"Cobalt % payable"}],"mode":"Actual", "chartRows":[],"grids":[{"index":"0","rows":[
            {"index":0,"cells":[{"colId":"MB-BMS-0002-mid","text":"68.20"}]},
            {"index":1,"cells":[{"colId":"date","text":"14 Oct 2026"},{"colId":"MB-BMS-0002-mid","text":"68.25"}]}]}]}
        anomalies=[]
        merged=m.merge_samples({},original,anomalies)
        merged=m.merge_samples(merged,extra,anomalies)
        self.assertEqual(len(merged['grids'][0]['rows']),2)
        prices, _, warnings=m.read_snapshot({'widgets':[merged]},365,now=date(2026,10,16))
        self.assertEqual({(p.symbol,p.date) for p in prices},
                         {('MB-BMS-0001','2026-10-15'),('MB-BMS-0002','2026-10-15'),('MB-BMS-0002','2026-10-14')})
        self.assertFalse(anomalies)

    def test_duplicates_and_export(self):
        prices, inventory, warnings=m.read_snapshot(self.sample(),365,now=date(2026,10,16))
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            diag={'widget_count':5,'found_symbols':[x.symbol for x in prices], 'warnings':warnings}
            m.save_sqlite(m.path_bundle(folder)['db'],prices,inventory,diag)
            m.save_sqlite(m.path_bundle(folder)['db'],prices,inventory,diag)
            m.export_files(folder)
            with closing(sqlite3.connect(m.path_bundle(folder)['db'])) as cx:
                self.assertEqual(cx.execute('select count(*) from prices').fetchone()[0],7)
                self.assertEqual(cx.execute('select count(*) from collection_runs').fetchone()[0],2)
            with m.path_bundle(folder)['csv'].open(encoding='utf-8-sig',newline='') as fp:
                self.assertEqual(len(list(csv.DictReader(fp))),7)
            with m.path_bundle(folder)['master'].open(encoding='utf-8-sig',newline='') as fp:
                self.assertEqual(len(list(csv.DictReader(fp))),7)

    def test_scroll_positions_bounded(self):
        self.assertEqual(m.positions(0,200),[0])
        self.assertEqual(m.positions(500,200)[-1],500)
        self.assertLessEqual(len(m.positions(1000000,200,limit=120)),120)

if __name__ == '__main__':unittest.main(verbosity=2)
