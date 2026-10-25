import tempfile
import unittest
from pathlib import Path


class SourceBundleTests(unittest.TestCase):
    def test_deterministic_bundle_restore_checks_every_source_byte(self):
        from scripts.build_source_bundle import write_bundle
        from bring_in.RESTORE_LATEST_SOURCE import restore_source
        files={'app.py':b'print("source")\n','docs/readme.md':'금속 중심'.encode()}
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);result=write_bundle(files,'a'*40,root/'build')
            before=Path(result['txt']).read_bytes()
            again=write_bundle(files,'a'*40,root/'build')
            self.assertEqual(before,Path(again['txt']).read_bytes())
            destination=root/'restored';manifest=restore_source(result['txt'],destination)
            self.assertEqual(manifest['source_commit'],'a'*40)
            for path,data in files.items():self.assertEqual((destination/path).read_bytes(),data)
            with self.assertRaises(FileExistsError):restore_source(result['txt'],destination)
            corrupted=root/'corrupt.txt';corrupted.write_bytes(before[:-12]+b'AAAAAAAAAAAA')
            with self.assertRaises(ValueError):restore_source(corrupted,root/'bad')
            self.assertFalse((root/'bad').exists())

    def test_reject_unsafe_paths_before_creating_output(self):
        from scripts.build_source_bundle import write_bundle
        with tempfile.TemporaryDirectory() as t:
            for path in ('../escape.py','/absolute.py','folder\\escape.py'):
                with self.assertRaises(ValueError):write_bundle({path:b'x'},'a'*40,Path(t)/'out')


if __name__=='__main__':unittest.main()
