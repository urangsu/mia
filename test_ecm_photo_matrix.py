"""Photo-shaped synthetic matrix. Rows1/3 and ABC dates, row4 TODAY untouched."""
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock,patch
from ecm_excel_sync import ECMBlocked

KEYS=['FMB|MB-LI-0029|$/kg|Unspecified|MID','SMM|SMM-Li-LC-001|USD/t|Actual|AVG',
      'LME|LME_NI_CASH_ASK|USD/t|Official|ASK','SMM|SMM-NI-NC-001_NI_EQ_2232|USD/t Ni|Derived|AVG',
      'SMM|SMM-CO-CM-001|USD/t|Actual|AVG','FX_USD_KRW_per_1']
CATALOG=[('key','name','conditions')]+list(zip(KEYS,['탄산리튬','탄산리튬','니켈 Cash Ask','니켈 환산','코발트','USD'],
    ['Lithium carbonate battery cif China','public average','Official Settlement','22.32%','China cobalt','KRW/1 USD']))
SOURCE=[('고시일','Li','SMM Li','Ni','Ni eq','Co','USD'),('','FMB','SMM','LME','SMM','SMM','SMBS'),('2026-10-27',13.7,14000,18000,19000,30000,1300)]


def matrix():
    return [[None,None,None,'탄산리튬','탄산리튬','탄산리튬','니켈','니켈','코발트','달러'],
        [None]*10,['연도','월','일','FMB(CIF)','SMM','SMM(증X)','LME','SMM','SMM','$'],
        [2026,10,28]+[None]*7,[2026,1,1]+[None]*7,[2026,10,27]+[None]*7,[2026,10,28]+[None]*7]


class PhotoMatrixTests(unittest.TestCase):
    def test_headers_1_and_3_and_abc_dates_choose_only_body_row(self):
        from ecm_matrix import build_matrix_plan
        plan=build_matrix_plan(SOURCE,CATALOG,matrix())
        self.assertEqual({e['row'] for e in plan['edits']},{6})
        self.assertEqual({e['col'] for e in plan['edits']},{4,5,7,8,9,10})
        self.assertEqual(next(e['incoming'] for e in plan['edits'] if e['col']==8),19000)
        self.assertFalse(plan['new_dates']);self.assertFalse(plan['new_columns'])
        self.assertTrue(any('증' in str(w) or 'VAT' in str(w) for w in plan['warnings']))

    def test_duplicates_below_five_block_but_today_row_does_not(self):
        from ecm_matrix import build_matrix_plan
        dest=matrix();dest.append(dest[5][:])
        with self.assertRaisesRegex(ECMBlocked,'중복'):build_matrix_plan(SOURCE,CATALOG,dest)

    def test_no_matching_date_does_not_append_or_fill_today(self):
        from ecm_matrix import build_matrix_plan
        source=SOURCE[:2]+[('2027-01-01',1,2,3,4,5,6)]
        plan=build_matrix_plan(source,CATALOG,matrix())
        self.assertFalse(plan['edits']);self.assertFalse(plan['new_dates'])
        self.assertTrue(plan['warnings'])

    def test_ambiguous_fmb_quotes_do_not_choose_one_arbitrarily(self):
        from ecm_matrix import build_matrix_plan
        key='FMB|MB-LI-OTHER|$/kg|Actual|MID'
        catalog=CATALOG+[(key,'탄산리튬','Lithium carbonate battery cif China')]
        source=[tuple(r)+(('extra',) if i==0 else ('FMB',) if i==1 else (99,)) for i,r in enumerate(SOURCE)]
        plan=build_matrix_plan(source,catalog,matrix())
        self.assertFalse(any(e['col']==4 for e in plan['edits']))
        self.assertTrue(any('후보' in str(w) for w in plan['warnings']))

    def test_formula_and_text_are_never_overwritten(self):
        from ecm_matrix import build_matrix_plan
        for text in ('=A1','사용자 메모'):
            dest=matrix();dest[5][3]=text
            with self.assertRaises(ECMBlocked):build_matrix_plan(SOURCE,CATALOG,dest)

    def test_xlsm_validation_and_generated_ecm_name_binding(self):
        from app_settings import validate
        from ecm_binding import select_observed
        cfg=validate(dict(data_dir='synthetic',ecm_title='금속시세TEST.xlsm',ecm_search='금속시세TEST'),'ecm_preview')
        self.assertEqual(cfg['ecm_title'],'금속시세TEST.xlsm')
        name='금속시세TEST_0900bf4bade0d1cd_usr1100bf4ba0198871.xlsm'
        book=dict(name=name,full_name='C:/ECM/'+name,excel_hwnd=10,read_only=False)
        self.assertEqual(select_observed([],[book],'금속시세TEST.xlsm')['name'],name)
        with self.assertRaises(RuntimeError):select_observed([book],[book],'금속시세TEST.xlsm')

    def test_xlsm_link_name_never_accepts_xlsx_with_same_stem(self):
        from ecm_names import file_matches
        self.assertTrue(file_matches('금속시세TEST.xlsm','금속시세TEST.xlsm'))
        self.assertFalse(file_matches('금속시세TEST.xlsx','금속시세TEST.xlsm'))
        self.assertFalse(file_matches('금속시세TEST.xlsm.exe','금속시세TEST.xlsm'))

    def test_xlsm_preview_expands_groups_and_binds_existing_sheet(self):
        from ecm_excel_sync import prepare_ecm_plan
        wb=MagicMock();wb.Name='금속시세TEST.xlsm';wb.FullName='C:/ECM/금속시세TEST.xlsm'
        wb.FileFormat=52;wb.HasVBProject=True;wb.Worksheets.Count=2
        first,second=MagicMock(),MagicMock()
        def worksheet(key):
            if key=='일별요약':raise KeyError(key)
            return first if key in ('금속시세',1) else second
        wb.Worksheets.side_effect=worksheet
        @contextmanager
        def attached(*args):yield wb
        with patch('ecm_excel_sync._attached_excel',attached),patch('ecm_excel_sync._snapshot_from_db',return_value=(SOURCE,CATALOG,())),patch('ecm_excel_sync._read_matrix',return_value=matrix()):
            plan=prepare_ecm_plan('synthetic','금속시세TEST.xlsm',log=lambda _:None)
        self.assertEqual(plan['sheet'],'금속시세')
        self.assertEqual(plan['excel_file_format'],52);self.assertTrue(plan['has_vba'])
        self.assertEqual({e['row'] for e in plan['edits']},{6})
        first.Outline.ShowLevels.assert_called_once_with(8,8)
        second.Outline.ShowLevels.assert_called_once_with(8,8)
        wb.Save.assert_not_called();wb.SaveAs.assert_not_called()

    def test_macro_format_change_blocks_before_plan(self):
        from ecm_excel_sync import _macro_signature
        wb=MagicMock();wb.Name='금속시세TEST.xlsm';wb.FileFormat=51;wb.HasVBProject=True
        with self.assertRaisesRegex(ECMBlocked,'52'):_macro_signature(wb)


if __name__=='__main__':unittest.main()
