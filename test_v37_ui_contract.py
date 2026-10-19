import unittest
from unittest.mock import patch

class UIContract(unittest.TestCase):
    def test_dark_design_tokens(self):
        import gui_v37 as gui
        self.assertEqual(gui.WHITE,'#101013')
        self.assertEqual(gui.SOFT,'#202025')
        self.assertEqual(gui.BLUE,'#4391ff')

    def test_report_sheets_are_managed(self):
        from excel_secure import MANAGED
        from report_model import REPORT_NAMES
        self.assertTrue(set(REPORT_NAMES).issubset(MANAGED))
        self.assertIn('워크스페이스원본',MANAGED)

    def test_ecm_source_uses_same_snapshot_builder(self):
        import ecm_excel_sync as e
        from types import SimpleNamespace
        with patch('report_model.build_context',return_value=SimpleNamespace()) as build, patch(
                'report_model.make_workbook_sheets',return_value={'일별요약':[['date']],'가격열설정':[['key']]}) as sheets:
            self.assertEqual(e._snapshot_from_db('not-used'),([['date']],[['key']]))
            build.assert_called_once();sheets.assert_called_once()

    def test_headerless_user_column_blocks_expansion(self):
        from types import SimpleNamespace
        from excel_secure import guard_expansion,SecureExcelError
        ws=SimpleNamespace(UsedRange=SimpleNamespace(Column=1,Row=1,Columns=SimpleNamespace(Count=5),Rows=SimpleNamespace(Count=6)))
        ws.Cells=lambda r,c:(r,c)
        ws.Range=lambda a,b:(a,b)
        ws.Application=SimpleNamespace(WorksheetFunction=SimpleNamespace(CountA=lambda r:1))
        with self.assertRaises(SecureExcelError):
            guard_expansion(ws,{'new_columns':[{'col':4}],'new_dates':[]})

if __name__=='__main__':unittest.main()
