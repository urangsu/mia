"""Presentation values must not fabricate data or lose zero-prefixed codes."""
import importlib.util
import unittest


@unittest.skipUnless(importlib.util.find_spec('PySide6'), 'Qt desktop dependency not installed')
class TableTests(unittest.TestCase):
    def test_model_preserves_codes_and_shows_missing_not_zero(self):
        from desktop_tables import TableModel
        from PySide6.QtCore import Qt
        model=TableModel();model.replace([('코드','수치'),('005490',None)])
        self.assertEqual(model.data(model.index(0,0),Qt.DisplayRole),'005490')
        self.assertEqual(model.data(model.index(0,1),Qt.DisplayRole),'—')

    def test_numeric_sort_role_and_signed_color(self):
        from desktop_tables import TableModel
        from PySide6.QtCore import Qt
        model=TableModel();model.replace([('전일대비',),(-12.5,),(10,)])
        self.assertEqual(model.data(model.index(0,0),Qt.UserRole),-12.5)
        self.assertEqual(model.data(model.index(0,0),Qt.ForegroundRole).name(),'#4391ff')
        self.assertEqual(model.data(model.index(1,0),Qt.ForegroundRole).name(),'#f5445a')

if __name__=='__main__':unittest.main()
