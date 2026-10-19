import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import FastmarketsCollector_v3_7 as entry

class CLITests(unittest.TestCase):
    def test_report_filter_cannot_narrow_cumulative(self):
        with self.assertRaises(SystemExit) as ctx:entry.main(['--export-only','--start','2026-01-01'])
        self.assertEqual(ctx.exception.code,2)
    def test_report_retry_never_creates_browser(self):
        with patch.object(entry.core,'ChromeSession') as browser,patch('pipeline_v37.export_only',return_value={'status':'complete'}):
            self.assertEqual(entry.main(['--reports-only']),0);browser.assert_not_called()
    def test_evidence_missingdb_readonly(self):
        from collect_evidence_v37 import inspect
        with tempfile.TemporaryDirectory() as t:
            self.assertFalse(inspect(t)['db_exists']);self.assertEqual(list(Path(t).iterdir()),[])
    def test_performance_structure(self):
        from benchmark_v37 import run
        r=run();self.assertEqual(r['failure_rate'],0);self.assertEqual(r['after_numeric_write_calls'],2)

if __name__=='__main__':unittest.main()
