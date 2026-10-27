"""Synthetic LME observations only; no public-site or subscribed data claims."""
import sqlite3
from contextlib import closing
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

URL='https://www.lme.com/Market-data/Reports-and-data/LME-Official-Prices#LME+Official+prices'
COLS=('instrument_id','market_date','metal','contract','side','value','unit','currency',
      'price_type','is_settlement','captured_at','source_url','raw_json')


def observation(metal='Nickel',contract='Cash',side='Ask',value='100.25',day='2026-10-26',**changes):
    code={'Nickel':'NI','Copper':'CU','Cobalt':'CO'}[metal]
    row=dict(instrument_id=f'LME_{code}_{"CASH" if contract=="Cash" else "3M"}_{side.upper()}',
        market_date=day,metal=metal,contract=contract,side=side,value=value,unit='USD/t',currency='USD',
        price_type='Official',is_settlement=int(contract=='Cash' and side=='Ask'),
        captured_at='2026-10-27T08:30:00+09:00',source_url=URL,raw_json='{}')
    row.update(changes)
    return row


def sheet(rows):
    # Exercise the same SQLite text/boolean row boundary as the collector adapter.
    with closing(sqlite3.connect(':memory:')) as cx:
        cx.execute('CREATE TABLE lme_official_prices ('+','.join(COLS)+')')
        cx.executemany('INSERT INTO lme_official_prices VALUES ('+','.join('?' for _ in COLS)+')',
                       [tuple(row[k] for k in COLS) for row in rows])
        return [COLS]+cx.execute('SELECT * FROM lme_official_prices').fetchall()


class LMEDashboardTests(unittest.TestCase):
    def dashboard(self,rows):
        from metal_dashboard import dashboard_data
        return dashboard_data(SimpleNamespace(snapshot_id='fixture',_sheets={'LME_공식원본':sheet(rows)}))

    def test_six_ask_series_contracts_units_settlement_and_coverage(self):
        rows=[observation(metal=metal,contract=contract) for metal in ('Nickel','Copper','Cobalt') for contract in ('Cash','3-month')]
        result=self.dashboard(rows)
        self.assertEqual(len(result['series']),6)
        for entry in result['series']:
            self.assertEqual(entry['source'],'LME')
            self.assertEqual(entry['source_url'],URL)
            self.assertEqual(entry['unit'],'USD/t')
            self.assertIn(entry['contract'],entry['name'])
            self.assertIn('Ask',entry['name'])
            self.assertEqual(entry['is_settlement'],entry['contract']=='Cash')
            self.assertEqual(entry['points'][0]['value'],100.25)
        coverage=[c for c in result['coverage'] if c['source']=='LME']
        self.assertEqual(len(coverage),3)
        self.assertTrue(all(c['status']=='captured' and c['count']==2 for c in coverage))

    def test_collector_storage_adapter_loads_twelve_separate_series(self):
        import lme_official
        from metal_dashboard import dashboard_data
        rows=[observation(metal=m,contract=c,side=s) for m in ('Nickel','Copper','Cobalt')
              for c in ('Cash','3-month') for s in ('Ask','Bid')]
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'synthetic.sqlite3'
            lme_official.save_rows(db,rows)
            loaded=lme_official.load_rows(db)
            raw=[COLS]+[tuple(row[column] for column in COLS) for row in loaded]
            result=dashboard_data(SimpleNamespace(snapshot_id='adapter-fixture',_sheets={'LME_공식원본':raw}))
        self.assertEqual(len(result['series']),12)
        self.assertEqual([c['count'] for c in result['coverage'] if c['source']=='LME'],[4,4,4])

    def test_bid_is_distinct_selectable_and_primary_asks_sort_first(self):
        rows=[observation(contract=c,side=s,value=v) for c,s,v in
              [('3-month','Bid','90'),('Cash','Bid','91'),('3-month','Ask','110'),('Cash','Ask','111')]]
        result=self.dashboard(rows)
        self.assertEqual([(s['contract'],s['side']) for s in result['series']],
                         [('Cash','Ask'),('3-month','Ask'),('Cash','Bid'),('3-month','Bid')])
        self.assertEqual([s['points'][0]['value'] for s in result['series']],[111,110,91,90])
        self.assertEqual(len({s['id'] for s in result['series']}),4)

    def test_missing_and_conflicting_values_never_zero_or_average(self):
        rows=[observation(value='100',day='2026-10-23'),observation(value=None),observation(value='0',day='2026-10-27'),
              observation(value='110',day='2026-10-28'),observation(value='120',day='2026-10-28')]
        points=self.dashboard(rows)['series'][0]['points']
        self.assertEqual([p['value'] for p in points],[100,None,None,None])
        self.assertEqual(points[-1]['status'],'conflict')

    def test_decimal_conflict_not_hidden_by_float_display_rounding(self):
        result=self.dashboard([observation(value='100.000000000000001'),
                               observation(value='100.000000000000002')])
        self.assertIsNone(result['series'][0]['points'][0]['value'])
        self.assertEqual(result['series'][0]['points'][0]['status'],'conflict')

    def test_wrong_provider_contract_units_or_identity_not_presented(self):
        rows=[observation(source_url='https://example.com/prices'),observation(unit='USD/kg'),
              observation(instrument_id='LME_NI_3M_ASK'),observation(price_type='Closing'),
              observation(is_settlement=0)]
        result=self.dashboard(rows)
        self.assertEqual(result['series'],[])
        self.assertTrue(all(c['status']=='missing' for c in result['coverage'] if c['source']=='LME'))

    def test_absence_is_missing_observations_not_unsupported(self):
        result=self.dashboard([])
        lme=[c for c in result['coverage'] if c['source']=='LME']
        self.assertTrue(all(c['count']==0 and c['status']=='missing' for c in lme))
        self.assertTrue(all('저장 관측 없음' in c['reason'] for c in lme))

    def test_lme_and_fmb_do_not_fill_or_alias_each_others_values(self):
        from test_metal_dashboard import MetalDashboardTests
        from metal_dashboard import dashboard_data
        with tempfile.TemporaryDirectory() as folder:
            context=MetalDashboardTests().context(folder)
            before=dashboard_data(context)
            sheets=dict(context._sheets,LME_공식원본=sheet([observation()]))
            result=dashboard_data(replace(context,_sheets=sheets))
        self.assertEqual([s for s in result['series'] if s['source']=='FMB'],before['series'])
        self.assertEqual(len([s for s in result['series'] if s['source']=='LME']),1)
        self.assertEqual(result['snapshot_id'],context.snapshot_id)

    def test_actual_qt_panel_selects_distinct_contract_side_series(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        from desktop_metals import MetalPanel
        self.__class__.app=QApplication.instance() or QApplication([])
        panel=MetalPanel()
        result=self.dashboard([observation(contract=c,side=s,value=v) for c,s,v in
            [('Cash','Ask','111'),('3-month','Ask','110'),('Cash','Bid','91'),('3-month','Bid','90')]])
        panel.set_data(result);panel.group.setCurrentText('니켈')
        self.assertEqual(panel.product.count(),4)
        self.assertIn('Cash Ask',panel.product.currentText())
        self.assertEqual(panel.history.model.rows[0][1],111)
        panel.product.setCurrentIndex(1)
        self.assertIn('3-month Ask',panel.product.currentText())
        self.assertEqual(panel.history.model.rows[0][1],110)
        panel.close()


if __name__=='__main__':unittest.main()
