import unittest
from ecm_binding import select_observed

def item(path='C:/ECM/cache/book.xlsx',hwnd=10):
    return {'name':'book.xlsx','full_name':path,'excel_hwnd':hwnd,'read_only':False}

class BindingTests(unittest.TestCase):
    def test_observed_new_workbook(self):
        result=select_observed([], [item()], 'book.xlsx', 'C:/local/book.xlsx')
        self.assertEqual(result['origin'],'observed_ecm_open')
    def test_existing_unbound_same_name_rejected(self):
        with self.assertRaises(RuntimeError):select_observed([item()],[item()],'book.xlsx')
    def test_local_source_rejected(self):
        with self.assertRaises(RuntimeError):select_observed([],[item()],'book.xlsx','C:/ECM/cache/book.xlsx')
    def test_known_binding_only_same_excel_instance(self):
        prior=dict(item(),origin='observed_ecm_open')
        self.assertEqual(select_observed([item()],[item()],'book.xlsx',prior=prior)['excel_hwnd'],10)
        with self.assertRaises(RuntimeError):select_observed([item(hwnd=20)],[item(hwnd=20)],'book.xlsx',prior=prior)
    def test_multiple_fresh_rejected(self):
        with self.assertRaises(RuntimeError):select_observed([],[item(),item('C:/Other/book.xlsx')],'book.xlsx')

if __name__=='__main__':unittest.main()
