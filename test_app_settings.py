import tempfile
import unittest
from pathlib import Path
from app_settings import load, save, validate


class SettingsFileTests(unittest.TestCase):
    def test_real_atomic_roundtrip_and_extensions(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'settings.json'
            save(path,{'naver_enabled':False,'report_dir':'reports','lookback_days':7})
            values=load(path,{'data_dir':t})
            self.assertIs(values['naver_enabled'],False)
            self.assertEqual(values['report_dir'],'reports')
            self.assertEqual(values['lookback_days'],7)
            self.assertFalse(list(Path(t).glob('*.tmp')))

    def test_corrupt_original_is_not_overwritten_by_load(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'settings.json'
            path.write_text('{synthetic broken',encoding='utf8')
            before=path.read_bytes()
            self.assertIn('_settings_warning',load(path,{}))
            self.assertEqual(path.read_bytes(),before)

    def test_report_validation_does_not_require_ecm_fields(self):
        cfg=validate({'data_dir':'synthetic','ecm_title':'','ecm_search':''},'reports')
        self.assertEqual(cfg['ecm_title'],'')

if __name__=='__main__':unittest.main()
